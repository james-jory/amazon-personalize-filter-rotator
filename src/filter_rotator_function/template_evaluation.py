# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from simpleeval import simple_eval, DEFAULT_FUNCTIONS, DEFAULT_NAMES
import datetime
from dateutil.parser import parse
import re
from typing import Dict

"""
This script includes the utilities and functions for evaluating expressions/templates.
"""
def _unixtime(s):
    if isinstance(s, str):
        return parse(s).timestamp()
    if isinstance(s, datetime.time) or isinstance(s, datetime.date):
        return s.timestamp()
    return s

def _datetime_format(d, pattern: str):
    return d.strftime(pattern)

def _starts_with(s: str, prefix: str):
    return s.startswith(prefix)

def _ends_with(s: str, suffix: str):
    return s.endswith(suffix)

def _timedelta_days(v: int):
    return datetime.timedelta(days=v)

def _timedelta_hours(v: int):
    return datetime.timedelta(hours=v)

def _timedelta_minutes(v: int):
    return datetime.timedelta(minutes=v)

def _timedelta_seconds(v: int):
    return datetime.timedelta(seconds=v)

def _end(s: str, num: int):
    return s[-abs(num):]

def _start(s: str, num: int):
    return s[0:num]

def eval_expression(s: str, names: Dict = None):
    """
    Customizes the functions and names available in
    expression and evaluates an expression.
    """
    functions = DEFAULT_FUNCTIONS.copy()
    functions.update(
        unixtime=_unixtime,
        datetime_format=_datetime_format,
        starts_with=_starts_with,
        ends_with=_ends_with,
        start=_start,
        end=_end,
        timedelta_days=_timedelta_days,
        timedelta_hours=_timedelta_hours,
        timedelta_minutes=_timedelta_minutes,
        timedelta_seconds=_timedelta_seconds
    )

    names_combined = DEFAULT_NAMES.copy()
    names_combined.update(
        now=datetime.datetime.now()
    )

    if names:
         names_combined.update(names)

    return simple_eval(s, functions=functions, names=names_combined)

def eval_template(s: str, names: Dict = None):
    """
    Processes a template that includes zero or more expressions wrapped in handlebars ("{{ }}")
    where each embedded expression is replaced by the resolved expression.
    """
    return re.sub(r'\{\{([^\}]*)\}\}', lambda m: str(eval_expression(m.group(1), names)), s)
