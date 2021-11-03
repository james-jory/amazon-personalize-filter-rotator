# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3
from aws_lambda_powertools import Logger
from template_evaluation import eval_expression, eval_template

logger = Logger()
personalize = boto3.client('personalize')

@logger.inject_lambda_context(log_event=True)
def lambda_handler(event, _):
    dataset_group_arn = event["datasetGroupArn"]
    current_filter_name_template = event["currentFilterNameTemplate"]
    current_filter_expression_template = event["currentFilterExpressionTemplate"]
    delete_filter_match_template = event["deleteFilterMatchTemplate"]

    current_filter_name = eval_template(current_filter_name_template)
    logger.info('Current filter name: %s', current_filter_name)

    current_filter_exists = False

    filters_response = personalize.list_filters(datasetGroupArn = dataset_group_arn, maxResults = 100)
    for filter in filters_response['Filters']:
        if filter['name'] == current_filter_name:
            logger.info('Current filter %s already exists; skipping creation', current_filter_name)
            current_filter_exists = True
        elif delete_filter_match_template:
            delete_match = eval_expression(delete_filter_match_template, {'filter': filter})

            if delete_match:
                logger.info('Filter %s matched the delete filter template; deleting', filter['filterArn'])
                personalize.delete_filter(filterArn = filter['filterArn'])

    if not current_filter_exists:
        logger.info('Current filter %s does not exist; creating', current_filter_exists)

        expression = eval_template(current_filter_expression_template)

        response = personalize.create_filter(
            datasetGroupArn = dataset_group_arn,
            filterExpression = expression,
            name = current_filter_name
        )

        logger.info(response)
