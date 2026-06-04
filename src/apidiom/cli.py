import click


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """apidiom turns API documentation into idiomatic API clients."""
