"""Export the authoritative schema without starting a server or reading services."""

import json

from edgeeagle_api.main import create_app


def main() -> None:
    print(json.dumps(create_app().openapi(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
