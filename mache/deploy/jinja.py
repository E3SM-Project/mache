from jinja2 import Environment, StrictUndefined


def define_square_bracket_environment() -> Environment:
    """
    Define a Jinja2 environment that uses square brackets for delimiters.

    This is useful for rendering double templates that also contain curly-brace
    Jinja syntax that should be preserved for later rendering.

    Returns
    -------
    jinja2.Environment
        A Jinja2 environment with square-bracket delimiters.
    """
    return Environment(
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        variable_start_string='[[',
        variable_end_string=']]',
        block_start_string='[%',
        block_end_string='%]',
        comment_start_string='[#',
        comment_end_string='#]',
    )
