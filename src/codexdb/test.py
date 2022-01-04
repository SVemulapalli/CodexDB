'''
Created on Jan 3, 2022

@author: immanueltrummer
'''
import argparse
import codexdb.catalog
import codexdb.engine
import json
import os
import openai
import pandas as pd


def db_info(schema, files):
    """ Generate description of database.
    
    Args:
        schema: description of database schema
        files: names to files storing tables
    
    Returns:
        list of description lines
    """
    lines = []
    tables = schema['table_names_original']
    all_columns = schema['column_names_original']
    nr_tables = len(tables)
    for tbl_idx in range(nr_tables):
        filename = files[tbl_idx]
        tbl_name = tables[tbl_idx]
        tbl_columns = [c[1] for c in all_columns if c[0] == tbl_idx]
        col_list = ', '.join(tbl_columns)
        line = f'Table {tbl_name} with columns {col_list}, ' \
            f'stored in {filename}.'
        lines.append(line)
    return lines


def get_prompt(schema, files, question, query):
    """ Generate prompt for processing specific query. 
    
    Args:
        schema: description of database schema
        files: location of data files for tables
        question: natural language query
        query: SQL translation of query
    
    Returns:
        Prompt generating code for executing query
    """
    prompt_parts = []
    prompt_parts.append(
        f'"""\nThis Python program answers the query "{query}" ' +\
        f'on the following tables:')
    prompt_parts += db_info(schema, files)
    prompt_parts.append('1. Read data for relevant tables.')
    prompt_parts.append('2. Process the query efficiently.')
    prompt_parts.append('3. Write query result to "results.csv".')
    prompt_parts.append('"""')
    prompt_parts.append('')
    prompt_parts.append('--- Start of Python program ---')
    return '\n'.join(prompt_parts)


def generate_code(prompt):
    """ Generate code by completing given prompt. 
    
    Args:
        prompt: initiate generation with this prompt
    
    Returns:
        generated code, following prompt
    """
    try:
        print(f'\nPrompt:\n*******\n{prompt}\n*******')
        response = openai.Completion.create(
            engine='davinci-codex', prompt=prompt, 
            temperature=0, max_tokens=400,
            stop='--- End of Python program ---')
        return response['choices'][0]['text']
    except Exception as e:
        print(f'Error querying Codex: {e}')
        return ''


def result_cmp(ref_output, cmp_output):
    """ Compares query result output against reference.
    
    Args:
        ref_output: reference query result
        cmp_output: compare this against reference
    
    Returns:
        Comparable flag, number of differences, similarity
    """
    print(f'-- CodexDB output:\n{cmp_output}\n--\n')
    print(f'-- Reference output:\n{ref_output}\n--\n')
    ref_output.reindex()
    cmp_output.reindex()
    ref_output.columns = [0] * ref_output.shape[1]
    cmp_output.columns = [0] * cmp_output.shape[1]
    try:
        diffs = ref_output.compare(cmp_output, align_axis=0)
        print(f'-- Differences:\n{diffs}\n--\n')
        nr_diffs = diffs.shape[0]
        return True, nr_diffs, 1.0/(nr_diffs+1)
    except:
        print('(Incomparable)')
        return False, -1, 0


if __name__ == '__main__':
    
    parser = argparse.ArgumentParser()
    parser.add_argument('ai_key', type=str, help='Key for OpenAI access')
    parser.add_argument('data_dir', type=str, help='Data directory')
    parser.add_argument('test_path', type=str, help='Path to test case file')
    args = parser.parse_args()
    
    os.environ['KMP_DUPLICATE_LIB_OK']='True'
    openai.api_key = args.ai_key
    with open(args.test_path) as file:
        test_cases = json.load(file)

    catalog = codexdb.catalog.DbCatalog(args.data_dir)
    engine = codexdb.engine.ExecuteCode(catalog)

    with open('sql_log', 'w') as log_file:
        for i in range(20):
            cur_test = test_cases[i]
            db_id = cur_test['db_id']
            schema = catalog.schema(db_id)
            files = catalog.files(db_id)
            question = cur_test['question']
            query = cur_test['query']
            
            prompt = get_prompt(schema, files, question, query)
            code = generate_code(prompt)
            print(f'Generated code:\n-------\n{code}\n-------\n')
            success, output, elapsed_s = engine.execute(db_id, 'python', code)
            print(f'CodexDB successful: {success} in {elapsed_s}s')
            
            ref_output = pd.DataFrame(cur_test['results'])
            comparable, nr_diffs, similarity = result_cmp(ref_output, output)
            log_file.write(
                f'{success}\t{len(output)}\t{comparable}\t' +\
                f'{nr_diffs}\t{similarity}\t{elapsed_s}\n')