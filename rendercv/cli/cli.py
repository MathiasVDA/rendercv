"""
This module contains the functions and classes that handle the command line interface
(CLI) of RenderCV. It uses [Typer](https://typer.tiangolo.com/) to create the CLI and
[Rich](https://rich.readthedocs.io/en/latest/) to provide a nice looking terminal
output.
"""

import functools
import json
import os
import pathlib
import re
import shutil
import urllib.request
from typing import Annotated, Callable, Optional

import jinja2
import pydantic
import rich.console
import rich.live
import rich.panel
import rich.progress
import rich.table
import rich.text
import ruamel.yaml
import ruamel.yaml.parser
import typer
from rich import print

from . import __version__
from . import data_models as dm
from . import renderer as r

def get_latest_version_number_from_pypi() -> Optional[str]:
    """Get the latest version number of RenderCV from PyPI.

    Example:
        ```python
        get_latest_version_number_from_pypi()
        ```
        will return:
        `#!python "1.1"`

    Returns:
        Optional[str]: The latest version number of RenderCV from PyPI. Returns None if
            the version number cannot be fetched.
    """
    version = None
    url = "https://pypi.org/pypi/rendercv/json"
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read()
            encoding = response.info().get_content_charset("utf-8")
            json_data = json.loads(data.decode(encoding))
            version = json_data["info"]["version"]
    except Exception:
        pass

    return version


def warn_if_new_version_is_available() -> bool:
    """Check if a new version of RenderCV is available and print a warning message if
    there is a new version. Also, return True if there is a new version, and False
    otherwise.

    Returns:
        bool: True if there is a new version, and False otherwise.
    """
    latest_version = get_latest_version_number_from_pypi()
    if latest_version is not None and __version__ != latest_version:
        warning(
            f"A new version of RenderCV is available! You are using v{__version__},"
            f" and the latest version is v{latest_version}."
        )
        return True
    else:
        return False


def welcome():
    """Print a welcome message to the terminal."""
    warn_if_new_version_is_available()

    table = rich.table.Table(
        title=(
            "\nWelcome to [bold]Render[dodger_blue3]CV[/dodger_blue3][/bold]! Some"
            " useful links:"
        ),
        title_justify="left",
    )

    table.add_column("Title", style="magenta", justify="left")
    table.add_column("Link", style="cyan", justify="right", no_wrap=True)

    table.add_row("Documentation", "https://docs.rendercv.com")
    table.add_row("Source code", "https://github.com/sinaatalay/rendercv/")
    table.add_row("Bug reports", "https://github.com/sinaatalay/rendercv/issues/")
    table.add_row("Feature requests", "https://github.com/sinaatalay/rendercv/issues/")
    table.add_row("Discussions", "https://github.com/sinaatalay/rendercv/discussions/")
    table.add_row(
        "RenderCV Pipeline", "https://github.com/sinaatalay/rendercv-pipeline/"
    )

    print(table)


def warning(text: str):
    """Print a warning message to the terminal.

    Args:
        text (str): The text of the warning message.
    """
    print(f"[bold yellow]{text}")


def error(text: Optional[str] = None, exception: Optional[Exception] = None):
    """Print an error message to the terminal and exit the program. If an exception is
    given, then print the exception's message as well. If neither text nor exception is
    given, then print an empty line and exit the program.

    Args:
        text (str): The text of the error message.
        exception (Exception, optional): An exception object. Defaults to None.
    """
    if exception is not None:
        exception_messages = [str(arg) for arg in exception.args]
        exception_message = "\n\n".join(exception_messages)
        if text is None:
            text = "An error occurred:"

        print(
            f"\n[bold red]{text}[/bold red]\n\n[orange4]{exception_message}[/orange4]\n"
        )
    elif text is not None:
        print(f"\n[bold red]{text}\n")
    else:
        print()

    raise typer.Exit(code=4)


def information(text: str):
    """Print an information message to the terminal.

    Args:
        text (str): The text of the information message.
    """
    print(f"[yellow]{text}")


def get_error_message_and_location_and_value_from_a_custom_error(
    error_string: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Look at a string and figure out if it's a custom error message that has been
    sent from [`data_models.py`](data_models.md). If it is, then return the custom
    message, location, and the input value.

    This is done because sometimes we raise an error about a specific field in the model
    validation level, but Pydantic doesn't give us the exact location of the error
    because it's a model-level error. So, we raise a custom error with three string
    arguments: message, location, and input value. Those arguments then combined into a
    string by Python. This function is used to parse that custom error message and
    return the three values.

    Args:
        error_string (str): The error message.
    Returns:
        tuple[Optional[str], Optional[str], Optional[str]]: The custom message,
            location, and the input value.
    """
    pattern = r"""\(['"](.*)['"], '(.*)', '(.*)'\)"""
    match = re.search(pattern, error_string)
    if match:
        return match.group(1), match.group(2), match.group(3)
    else:
        return None, None, None


def handle_validation_error(exception: pydantic.ValidationError):
    """Take a Pydantic validation error and print the error messages in a nice table.

    Pydantic's `ValidationError` object is a complex object that contains a lot of
    information about the error. This function takes a `ValidationError` object and
    extracts the error messages, locations, and the input values. Then, it prints them
    in a nice table with [Rich](https://rich.readthedocs.io/en/latest/).

    Args:
        exception (pydantic.ValidationError): The Pydantic validation error object.
    """
    # This dictionary is used to convert the error messages that Pydantic returns to
    # more user-friendly messages.
    error_dictionary: dict[str, str] = {
        "Input should be 'present'": (
            "This is not a valid date! Please use either YYYY-MM-DD, YYYY-MM, or YYYY"
            ' format or "present"!'
        ),
        "Input should be a valid integer, unable to parse string as an integer": (
            "This is not a valid date! Please use either YYYY-MM-DD, YYYY-MM, or YYYY"
            " format!"
        ),
        "String should match pattern '\\d{4}-\\d{2}(-\\d{2})?'": (
            "This is not a valid date! Please use either YYYY-MM-DD, YYYY-MM, or YYYY"
            " format!"
        ),
        "URL scheme should be 'http' or 'https'": "This is not a valid URL!",
        "Field required": "This field is required!",
        "value is not a valid phone number": "This is not a valid phone number!",
        "month must be in 1..12": "The month must be between 1 and 12!",
        "day is out of range for month": "The day is out of range for the month!",
        "Extra inputs are not permitted": (
            "This field is unknown for this object! Please remove it."
        ),
        "Input should be a valid string": "This field should be a string!",
        "Input should be a valid list": (
            "This field should contain a list of items but it doesn't!"
        ),
    }

    unwanted_texts = ["value is not a valid email address: ", "Value error, "]

    # Check if this is a section error. If it is, we need to handle it differently.
    # This is needed because how dm.validate_section_input function raises an exception.
    # This is done to tell the user which which EntryType RenderCV excepts to see.
    errors = exception.errors()
    for error_object in errors.copy():
        if (
            "There are problems with the entries." in error_object["msg"]
            and "ctx" in error_object
        ):
            location = error_object["loc"]
            ctx_object = error_object["ctx"]
            if "error" in ctx_object:
                error_object = ctx_object["error"]
                if hasattr(error_object, "__cause__"):
                    cause_object = error_object.__cause__
                    cause_object_errors = cause_object.errors()
                    for cause_error_object in cause_object_errors:
                        # we use [1:] to avoid `entries` location. It is a location for
                        # RenderCV's own data model, not the user's data model.
                        cause_error_object["loc"] = tuple(
                            list(location) + list(cause_error_object["loc"][1:])
                        )
                    errors.extend(cause_object_errors)

    # some locations are not really the locations in the input file, but some
    # information about the model coming from Pydantic. We need to remove them.
    # (e.g. avoid stuff like .end_date.literal['present'])
    unwanted_locations = ["tagged-union", "list", "literal", "int", "constrained-str"]
    for error_object in errors:
        location = error_object["loc"]
        new_location = [str(location_element) for location_element in location]
        for location_element in location:
            location_element = str(location_element)
            for unwanted_location in unwanted_locations:
                if unwanted_location in location_element:
                    new_location.remove(location_element)
        error_object["loc"] = new_location  # type: ignore

    # Parse all the errors and create a new list of errors.
    new_errors: list[dict[str, str]] = []
    for error_object in errors:
        message = error_object["msg"]
        location = ".".join(error_object["loc"])  # type: ignore
        input = error_object["input"]

        # Check if this is a custom error message:
        custom_message, custom_location, custom_input_value = (
            get_error_message_and_location_and_value_from_a_custom_error(message)
        )
        if custom_message is not None:
            message = custom_message
            if custom_location:
                # If the custom location is not empty, then add it to the location.
                location = f"{location}.{custom_location}"
            input = custom_input_value

        # Don't show unwanted texts in the error message:
        for unwanted_text in unwanted_texts:
            message = message.replace(unwanted_text, "")

        # Convert the error message to a more user-friendly message if it's in the
        # error_dictionary:
        if message in error_dictionary:
            message = error_dictionary[message]

        # Special case for end_date because Pydantic returns multiple end_date errors
        # since it has multiple valid formats:
        if "end_date" in location:
            message = (
                "This is not a valid end date! Please use either YYYY-MM-DD, YYYY-MM,"
                ' or YYYY format or "present"!'
            )

        # If the input is a dictionary or a list (the model itself fails to validate),
        # then don't show the input. It looks confusing and it is not helpful.
        if isinstance(input, (dict, list)):
            input = ""

        new_error = {
            "loc": str(location),
            "msg": message,
            "input": str(input),
        }

        # if new_error is not in new_errors, then add it to new_errors
        if new_error not in new_errors:
            new_errors.append(new_error)

    # Print the errors in a nice table:
    table = rich.table.Table(
        title="[bold red]\nThere are some errors in the data model!\n",
        title_justify="left",
        show_lines=True,
    )
    table.add_column("Location", style="cyan", no_wrap=True)
    table.add_column("Input Value", style="magenta")
    table.add_column("Error Message", style="orange4")

    for error_object in new_errors:
        table.add_row(
            error_object["loc"],
            error_object["input"],
            error_object["msg"],
        )

    print(table)
    error()  # exit the program


def handle_exceptions(function: Callable) -> Callable:
    """Return a wrapper function that handles exceptions.

    A decorator in Python is a syntactic convenience that allows a Python to interpret
    the code below:

    ```python
    @handle_exceptions
    def my_function():
        pass
    ```
    as
    ```python
    handle_exceptions(my_function)()
    ```
    which is step by step equivalent to

    1.  Execute `#!python handle_exceptions(my_function)` which will return the
        function called `wrapper`.
    2.  Execute `#!python wrapper()`.

    Args:
        function (Callable): The function to be wrapped.
    Returns:
        Callable: The wrapped function.
    """

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            function(*args, **kwargs)
        except pydantic.ValidationError as e:
            handle_validation_error(e)
        except ruamel.yaml.YAMLError as e:
            error(
                "There is a YAML error in the input file!\n\nTry to use quotation marks"
                " to make sure the YAML parser understands the field is a string.",
                e,
            )
        except FileNotFoundError as e:
            error(e)
        except UnicodeDecodeError as e:
            # find the problematic character that cannot be decoded with utf-8
            bad_character = str(e.object[e.start : e.end])
            try:
                bad_character_context = str(e.object[e.start - 16 : e.end + 16])
            except IndexError:
                bad_character_context = ""

            error(
                "The input file contains a character that cannot be decoded with"
                f" UTF-8 ({bad_character}):\n {bad_character_context}",
            )
        except ValueError as e:
            error(e)
        except typer.Exit:
            pass
        except jinja2.exceptions.TemplateSyntaxError as e:
            error(
                f"There is a problem with the template ({e.filename}) at line"
                f" {e.lineno}!",
                e,
            )
        except RuntimeError as e:
            error(e)

    return wrapper


class LiveProgressReporter(rich.live.Live):
    """This class is a wrapper around `rich.live.Live` that provides the live progress
    reporting functionality.

    Args:
        number_of_steps (int): The number of steps to be finished.
    """

    def __init__(self, number_of_steps: int, end_message: str = "Your CV is rendered!"):
        class TimeElapsedColumn(rich.progress.ProgressColumn):
            def render(self, task: "rich.progress.Task") -> rich.text.Text:
                elapsed = task.finished_time if task.finished else task.elapsed
                delta = f"{elapsed:.1f} s"
                return rich.text.Text(str(delta), style="progress.elapsed")

        self.step_progress = rich.progress.Progress(
            TimeElapsedColumn(), rich.progress.TextColumn("{task.description}")
        )

        self.overall_progress = rich.progress.Progress(
            TimeElapsedColumn(),
            rich.progress.BarColumn(),
            rich.progress.TextColumn("{task.description}"),
        )

        self.group = rich.console.Group(
            rich.panel.Panel(rich.console.Group(self.step_progress)),
            self.overall_progress,
        )

        self.overall_task_id = self.overall_progress.add_task("", total=number_of_steps)
        self.number_of_steps = number_of_steps
        self.end_message = end_message
        self.current_step = 0
        self.overall_progress.update(
            self.overall_task_id,
            description=(
                f"[bold #AAAAAA]({self.current_step} out of"
                f" {self.number_of_steps} steps finished)"
            ),
        )
        super().__init__(self.group)

    def __enter__(self) -> "LiveProgressReporter":
        """Overwrite the `__enter__` method for the correct return type."""
        self.start(refresh=self._renderable is not None)
        return self

    def start_a_step(self, step_name: str):
        """Start a step and update the progress bars."""
        self.current_step_name = step_name
        self.current_step_id = self.step_progress.add_task(
            f"{self.current_step_name} has started."
        )

    def finish_the_current_step(self):
        """Finish the current step and update the progress bars."""
        self.step_progress.stop_task(self.current_step_id)
        self.step_progress.update(
            self.current_step_id, description=f"{self.current_step_name} has finished."
        )
        self.current_step += 1
        self.overall_progress.update(
            self.overall_task_id,
            description=(
                f"[bold #AAAAAA]({self.current_step} out of"
                f" {self.number_of_steps} steps finished)"
            ),
            advance=1,
        )
        if self.current_step == self.number_of_steps:
            self.end()

    def end(self):
        """End the live progress reporting."""
        self.overall_progress.update(
            self.overall_task_id,
            description=f"[yellow]{self.end_message}",
        )


def copy_templates(
    folder_name: str,
    copy_to: pathlib.Path,
    new_folder_name: Optional[str] = None,
    suppress_warning: bool = False,
) -> Optional[pathlib.Path]:
    """Copy one of the folders found in `rendercv.templates` to `copy_to`.

    Args:
        folder_name (str): The name of the folder to be copied.
        copy_to (pathlib.Path): The path to copy the folder to.
    Returns:
        Optional[pathlib.Path]: The path to the copied folder.
    """
    # copy the package's theme files to the current directory
    template_directory = pathlib.Path(__file__).parent / "themes" / folder_name
    if new_folder_name:
        destination = copy_to / new_folder_name
    else:
        destination = copy_to / folder_name

    if destination.exists():
        if not suppress_warning:
            if folder_name != "markdown":
                warning(
                    f'The theme folder "{folder_name}" already exists! New theme files'
                    " are not created."
                )
            else:
                warning(
                    'The folder "markdown" already exists! New markdown files are not'
                    " created."
                )

        return None
    else:
        # copy the folder but don't include __init__.py:
        shutil.copytree(
            template_directory,
            destination,
            ignore=shutil.ignore_patterns("__init__.py"),
        )

        return destination


def parse_data_model_override_arguments(
    extra_arguments: typer.Context,
) -> dict["str", "str"]:
    """Parse extra arguments as data model key and value pairs and return them as a
    dictionary.

    Args:
        extra_arguments (typer.Context): The extra arguments context.
    Returns:
        dict["str", "str"]: The key and value pairs.
    """
    key_and_values: dict["str", "str"] = dict()

    # `extra_arguments.args` is a list of arbitrary arguments that haven't been
    # specified in `cli_render_command` function's definition. They are used to allow
    # users to edit their data model in CLI. The elements with even indexes in this list
    # are keys that start with double dashed, such as
    # `--cv.sections.education.0.institution`. The following elements are the
    # corresponding values of the key, such as `"Bogazici University"`. The for loop
    # below parses `ctx.args` accordingly.

    if len(extra_arguments.args) % 2 != 0:
        error(
            "There is a problem with the extra arguments! Each key should have"
            " a corresponding value."
        )

    for i in range(0, len(extra_arguments.args), 2):
        key = extra_arguments.args[i]
        value = extra_arguments.args[i + 1]
        if not key.startswith("--"):
            error(f"The key ({key}) should start with double dashes!")

        key = key.replace("--", "")

        key_and_values[key] = value

    return key_and_values
