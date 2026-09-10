#!/usr/bin/env python
"""Sifo Drive — Django Management Utility"""

import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Make sure Django is installed and your "
            "virtual environment is activated. Run:\n"
            "  pip install -r requirements/development.txt"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
