""" Morph-KGC """

__author__ = "Julián Arenas-Guerrero"
__copyright__ = "Copyright (C) 2020 Julián Arenas-Guerrero"
__credits__ = ["Julián Arenas-Guerrero"]

__license__ = "Apache-2.0"
__maintainer__ = "Julián Arenas-Guerrero"
__email__ = "arenas.guerrero.julian@outlook.com"


import logging
import constants
import sys
import time
import pandas as pd
import multiprocessing as mp

from itertools import repeat
from urllib.parse import quote

from data_source import relational_source
import utils


def _get_references_in_mapping_rule(mapping_rule, only_subject_map=False):
    references = []
    if pd.notna(mapping_rule['subject_template']):
        references.extend(utils.get_references_in_template(str(mapping_rule['subject_template'])))
    elif pd.notna(mapping_rule['subject_reference']):
        references.append(str(mapping_rule['subject_reference']))

    if not only_subject_map:
        if pd.notna(mapping_rule['predicate_template']):
            references.extend(utils.get_references_in_template(str(mapping_rule['predicate_template'])))
        elif pd.notna(mapping_rule['predicate_reference']):
            references.append(str(mapping_rule['predicate_reference']))
        if pd.notna(mapping_rule['object_template']):
            references.extend(utils.get_references_in_template(str(mapping_rule['object_template'])))
        elif pd.notna(mapping_rule['object_reference']):
            references.append(str(mapping_rule['object_reference']))
        if pd.notna(mapping_rule['graph_template']):
            references.extend(utils.get_references_in_template(str(mapping_rule['graph_template'])))
        elif pd.notna(mapping_rule['graph_reference']):
            references.append(str(mapping_rule['graph_reference']))

    return set(references)


def _materialize_template(results_df, template, columns_alias='', termtype='http://www.w3.org/ns/r2rml#IRI', language_tag='', datatype=''):
    references = utils.get_references_in_template(str(template))

    if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#Literal':
        results_df['triple'] = results_df['triple'] + '"'
    else:
        results_df['triple'] = results_df['triple'] + '<'

    for reference in references:
        results_df['reference_results'] = results_df[columns_alias + reference]

        if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#IRI':
            results_df['reference_results'] = results_df['reference_results'].apply(lambda x: quote(x))

        splitted_template = template.split('{' + reference + '}')
        results_df['triple'] = results_df['triple'] + splitted_template[0] + results_df['reference_results']
        template = str('{' + reference + '}').join(splitted_template[1:])

    if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#Literal':
        results_df['triple'] = results_df['triple'] + '"'
        if pd.notna(language_tag):
            results_df['triple'] = results_df['triple'] + '@' + language_tag + ' '
        elif pd.notna(datatype):
            results_df['triple'] = results_df['triple'] + '^^<' + datatype + '> '
        else:
            results_df['triple'] = results_df['triple'] + ' '
    else:
        results_df['triple'] = results_df['triple'] + '> '

    return results_df


def _materialize_reference(results_df, reference, columns_alias='', termtype='http://www.w3.org/ns/r2rml#Literal', language_tag='', datatype=''):
    results_df['reference_results'] = results_df[columns_alias + str(reference)]

    if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#IRI':
        results_df['reference_results'] = results_df['reference_results'].apply(lambda x: quote(x, safe='://'))
        results_df['triple'] = results_df['triple'] + '<' + results_df['reference_results'] + '> '
    elif str(termtype).strip() == 'http://www.w3.org/ns/r2rml#Literal':
        results_df['triple'] = results_df['triple'] + '"' + results_df['reference_results'] + '"'
        if pd.notna(language_tag):
            results_df['triple'] = results_df['triple'] + '@' + language_tag + ' '
        elif pd.notna(datatype):
            results_df['triple'] = results_df['triple'] + '^^<' + datatype + '> '
        else:
            results_df['triple'] = results_df['triple'] + ' '

    return results_df


def _materialize_constant(results_df, constant, termtype='http://www.w3.org/ns/r2rml#IRI', language_tag='', datatype=''):
    if str(termtype).strip() == 'http://www.w3.org/ns/r2rml#Literal':
        complete_constant = '"' + constant + '"'

        if pd.notna(language_tag):
            complete_constant = complete_constant + '@' + language_tag + ' '
        elif pd.notna(datatype):
            complete_constant = complete_constant + '^^<' + datatype + '> '
        else:
            complete_constant = complete_constant + ' '
    else:
        complete_constant = '<' + str(constant) + '> '

    results_df['triple'] = results_df['triple'] + complete_constant

    return results_df


def _materialize_join_mapping_rule_terms(results_df, mapping_rule, parent_triples_map_rule):
    results_df['triple'] = ''
    if pd.notna(mapping_rule['subject_template']):
        results_df = _materialize_template(results_df, mapping_rule['subject_template'], termtype=mapping_rule['subject_termtype'], columns_alias='child_')
    elif pd.notna(mapping_rule['subject_constant']):
        results_df = _materialize_constant(results_df, mapping_rule['subject_constant'], termtype=mapping_rule['subject_termtype'])
    elif pd.notna(mapping_rule['subject_reference']):
        results_df = _materialize_reference(results_df, mapping_rule['subject_reference'], termtype=mapping_rule['subject_termtype'], columns_alias='child_')
    if pd.notna(mapping_rule['predicate_template']):
        results_df = _materialize_template(results_df, mapping_rule['predicate_template'], columns_alias='child_')
    elif pd.notna(mapping_rule['predicate_constant']):
        results_df = _materialize_constant(results_df, mapping_rule['predicate_constant'])
    elif pd.notna(mapping_rule['predicate_reference']):
        results_df = _materialize_reference(results_df, mapping_rule['predicate_reference'], termtype='http://www.w3.org/ns/r2rml#IRI', columns_alias='child_')
    if pd.notna(parent_triples_map_rule['subject_template']):
        results_df = _materialize_template(results_df, parent_triples_map_rule['subject_template'], termtype=parent_triples_map_rule['subject_termtype'], columns_alias='parent_')
    elif pd.notna(parent_triples_map_rule['subject_constant']):
        results_df = _materialize_constant(results_df, parent_triples_map_rule['subject_constant'], termtype=parent_triples_map_rule['subject_termtype'])
    elif pd.notna(parent_triples_map_rule['subject_reference']):
        results_df = _materialize_reference(results_df, parent_triples_map_rule['subject_reference'], termtype=parent_triples_map_rule['subject_termtype'], columns_alias='parent_')
    if pd.notna(mapping_rule['graph_template']):
        results_df = _materialize_template(results_df, mapping_rule['graph_template'], columns_alias='child_')
    elif pd.notna(mapping_rule['graph_constant']):
        if pd.notna(mapping_rule['graph_constant'] != 'http://www.w3.org/ns/r2rml#defaultGraph'):
            results_df = _materialize_constant(results_df, mapping_rule['graph_constant'])
    elif pd.notna(mapping_rule['graph_reference']):
        results_df = _materialize_reference(results_df, mapping_rule['graph_reference'], termtype='http://www.w3.org/ns/r2rml#IRI', columns_alias='child_')

    return set(results_df['triple'])


def _materialize_mapping_rule_terms(results_df, mapping_rule):
    results_df['triple'] = ''
    if pd.notna(mapping_rule['subject_template']):
        results_df = _materialize_template(results_df, mapping_rule['subject_template'], termtype=mapping_rule['subject_termtype'])
    elif pd.notna(mapping_rule['subject_constant']):
        results_df = _materialize_constant(results_df, mapping_rule['subject_constant'], termtype=mapping_rule['subject_termtype'])
    elif pd.notna(mapping_rule['subject_reference']):
        results_df = _materialize_reference(results_df, mapping_rule['subject_reference'], termtype=mapping_rule['subject_termtype'])
    if pd.notna(mapping_rule['predicate_template']):
        results_df = _materialize_template(results_df, mapping_rule['predicate_template'])
    elif pd.notna(mapping_rule['predicate_constant']):
        results_df = _materialize_constant(results_df, mapping_rule['predicate_constant'])
    elif pd.notna(mapping_rule['predicate_reference']):
        results_df = _materialize_reference(results_df, mapping_rule['predicate_reference'], termtype='http://www.w3.org/ns/r2rml#IRI')
    if pd.notna(mapping_rule['object_template']):
        results_df = _materialize_template(results_df, mapping_rule['object_template'], termtype=mapping_rule['object_termtype'], language_tag=mapping_rule['object_language'], datatype=mapping_rule['object_datatype'])
    elif pd.notna(mapping_rule['object_constant']):
        results_df = _materialize_constant(results_df, mapping_rule['object_constant'], termtype=mapping_rule['object_termtype'], language_tag=mapping_rule['object_language'], datatype=mapping_rule['object_datatype'])
    elif pd.notna(mapping_rule['object_reference']):
        results_df = _materialize_reference(results_df, mapping_rule['object_reference'], termtype=mapping_rule['object_termtype'], language_tag=mapping_rule['object_language'], datatype=mapping_rule['object_datatype'])
    if pd.notna(mapping_rule['graph_template']):
        results_df = _materialize_template(results_df, mapping_rule['graph_template'])
    elif pd.notna(mapping_rule['graph_constant']):
        if pd.notna(mapping_rule['graph_constant'] != 'http://www.w3.org/ns/r2rml#defaultGraph'):
            results_df = _materialize_constant(results_df, mapping_rule['graph_constant'])
    elif pd.notna(mapping_rule['graph_reference']):
        results_df = _materialize_reference(results_df, mapping_rule['graph_reference'], termtype='http://www.w3.org/ns/r2rml#IRI')

    return set(results_df['triple'])


def _materalize_push_down_sql_join(mapping_rule, parent_triples_map_rule, references, parent_references, config):
    for key, join_condition in eval(mapping_rule['join_conditions']).items():
        parent_references.add(join_condition['parent_value'])
        references.add(join_condition['child_value'])

    sql_query = relational_source.build_sql_join_query(config, mapping_rule, parent_triples_map_rule,
                                                       references, parent_references)
    db_connection = relational_source.relational_db_connection(config, mapping_rule['source_name'])
    for query_results_chunk_df in pd.read_sql(sql_query, con=db_connection,
                                              chunksize=int(config.get('CONFIGURATION', 'chunksize')),
                                              coerce_float=config.getboolean('CONFIGURATION', 'coerce_float')):
        query_results_chunk_df = utils.dataframe_columns_to_str(query_results_chunk_df)
        db_connection.close()

        return _materialize_join_mapping_rule_terms(query_results_chunk_df, mapping_rule, parent_triples_map_rule)


def _materialize_mapping_rule(mapping_rule, subject_maps_df, config):
    triples = set()

    references = _get_references_in_mapping_rule(mapping_rule)

    if pd.notna(mapping_rule['object_parent_triples_map']):
        parent_triples_map_rule = \
            subject_maps_df[subject_maps_df.triples_map_id == mapping_rule['object_parent_triples_map']].iloc[0]
        parent_references = _get_references_in_mapping_rule(parent_triples_map_rule, only_subject_map=True)

        if config.getboolean('CONFIGURATION', 'push_down_sql_joins') and \
                mapping_rule['source_type'] in constants.RELATIONAL_SOURCE_TYPES and \
                mapping_rule['source_name'] == parent_triples_map_rule['source_name']:
            triples.update(_materalize_push_down_sql_join(mapping_rule, parent_triples_map_rule, references,
                                                          parent_references, config))
        """
        else:
            references.add(list(eval(mapping_rule['join_conditions']).values())[0]['child_value'])
            parent_references.add(list(eval(mapping_rule['join_conditions']).values())[0]['parent_value'])

            if mapping_rule['source_type'] == 'mysql':
                sql_query = relational_source.build_sql_query(config, mapping_rule, references)
                db_connection = relational_source.relational_db_connection(config, mapping_rule['source_name'])
                result_chunks = pd.read_sql(sql_query, con=db_connection, chunksize=int(config.get('CONFIGURATION', 'chunksize')), coerce_float=config.getboolean('CONFIGURATION', 'coerce_float'))
            elif mapping_rule['source_type'] == 'CSV':
                result_chunks = pd.read_table(mapping_rule['data_source'], delimiter=',', usecols=references, engine='c', chunksize=int(config.get('CONFIGURATION', 'chunksize')))
            # ----------------------
            if parent_triples_map_rule['source_type'] == 'mysql':
                parent_sql_query = relational_source.build_sql_query(config, parent_triples_map_rule, parent_references)
                parent_db_connection = relational_source.relational_db_connection(config, parent_triples_map_rule['source_name'])
                parent_result_chunks = pd.read_sql(parent_sql_query, con=parent_db_connection, chunksize=int(config.get('CONFIGURATION', 'chunksize')), coerce_float=config.getboolean('CONFIGURATION', 'coerce_float'))
            elif parent_triples_map_rule['source_type'] == 'CSV':
                parent_result_chunks = pd.read_table(parent_triples_map_rule['data_source'], delimiter=',', usecols=parent_references, engine='c', chunksize=int(config.get('CONFIGURATION', 'chunksize')))
            # ----------------------

            for query_results_chunk_df in result_chunks:
                query_results_chunk_df = utils.dataframe_columns_to_str(query_results_chunk_df)
                query_results_chunk_df = query_results_chunk_df.add_prefix('child_')
                for parent_query_results_chunk_df in pd.read_table(parent_triples_map_rule['data_source'], delimiter=',', usecols=parent_references, engine='c', chunksize=int(config.get('CONFIGURATION', 'chunksize'))):
                    # TODO: when using chunks the number of result obtained is not correct
                    # read_table should directly be in this inner for

                    parent_query_results_chunk_df = utils.dataframe_columns_to_str(parent_query_results_chunk_df)
                    parent_query_results_chunk_df = parent_query_results_chunk_df.add_prefix('parent_')
                    # TODO: study merge options
                    merged_query_results_chunk_df = query_results_chunk_df.merge(parent_query_results_chunk_df, how='inner', left_on='child_'+list(eval(mapping_rule['join_conditions']).values())[0]['child_value'], right_on='parent_'+list(eval(mapping_rule['join_conditions']).values())[0]['parent_value'])

                    triples.update(_materialize_join_mapping_rule_terms(merged_query_results_chunk_df, mapping_rule, parent_triples_map_rule))

            if mapping_rule['source_type'] == 'mysql':
                db_connection.close()
            if parent_triples_map_rule['source_type'] == 'mysql':
                db_connection.close()
        """
    else:
        if mapping_rule['source_type'] == 'MYSQL':
            sql_query = relational_source.build_sql_query(config, mapping_rule, references)
            db_connection = relational_source.relational_db_connection(config, mapping_rule['source_name'])
            result_chunks = pd.read_sql(sql_query, con=db_connection, chunksize=int(config.get('CONFIGURATION', 'chunksize')), coerce_float=config.getboolean('CONFIGURATION', 'coerce_float'))
        elif mapping_rule['source_type'] == 'CSV':
            result_chunks = pd.read_table(mapping_rule['data_source'], delimiter=',', usecols=_get_references_in_mapping_rule(mapping_rule), engine='c', chunksize=int(config.get('CONFIGURATION', 'chunksize')))

        for query_results_chunk_df in result_chunks:
            query_results_chunk_df = utils.dataframe_columns_to_str(query_results_chunk_df)
            triples.update(_materialize_mapping_rule_terms(query_results_chunk_df, mapping_rule))

        if mapping_rule['source_type'] in constants.RELATIONAL_SOURCE_TYPES:
            db_connection.close()

    return triples


def _materialize_mapping_partition(mapping_partition, subject_maps_df, config):
    triples = set()
    for i, mapping_rule in mapping_partition.iterrows():
        start_time = time.time()
        triples.update(set(_materialize_mapping_rule(mapping_rule, subject_maps_df, config)))

        logging.debug(str(len(triples)) + ' triples generated for mapping rule `' + str(
            mapping_rule['id']) + '` in ' + utils.get_delta_time(start_time) + ' seconds.')

    utils.triples_to_file(triples, config, mapping_partition.iloc[0]['mapping_partition'])

    return len(triples)


class Materializer:

    def __init__(self, mappings_df, config):
        self.mappings_df = mappings_df
        self.config = config

        self.subject_maps_df = utils.get_subject_maps(mappings_df)
        self.mapping_partitions = [group for _, group in mappings_df.groupby(by='mapping_partition')]

        utils.clean_output_dir(config)

    def __str__(self):
        return str(self.mappings_df)

    def __repr__(self):
        return repr(self.mappings_df)

    def __len__(self):
        return len(self.mappings_df)

    def materialize(self):
        num_triples = 0
        for mapping_partition in self.mapping_partitions:
            num_triples += _materialize_mapping_partition(mapping_partition, self.subject_maps_df, self.config)

        logging.info('Number of triples generated in total: ' + str(num_triples) + '.')

    def materialize_concurrently(self):
        if self.config.get('CONFIGURATION', 'process_start_method') != 'default':
            mp.set_start_method(self.config.get('CONFIGURATION', 'process_start_method'))
        logging.debug("Parallelizing with " + self.config.get('CONFIGURATION','number_of_processes') + " cores. Using `"
                      + mp.get_start_method() + "` as process start method.")

        pool = mp.Pool(int(self.config.get('CONFIGURATION', 'number_of_processes')))
        if self.config.getboolean('CONFIGURATION', 'async'):
            logging.debug("Using 'async' for parallelization.")
            triples_res = pool.starmap_async(_materialize_mapping_partition,
                                             zip(self.mapping_partitions, repeat(self.subject_maps_df),
                                                 repeat(self.config)))
            num_triples = sum(triples_res.get())
            if not triples_res.successful():
                logging.critical("Aborting, `async` multiprocessing resulted in error.")
                sys.exit()
        else:
            num_triples = sum(pool.starmap(_materialize_mapping_partition,
                                           zip(self.mapping_partitions, repeat(self.subject_maps_df),
                                               repeat(self.config))))
        pool.close()
        pool.join()

        logging.info('Number of triples generated in total: ' + str(num_triples) + '.')
