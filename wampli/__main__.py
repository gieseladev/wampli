def main() -> None:
    """Run the wampli.cli.main function.

    In addition, make it possible to run without the -m flag.
    """
    try:
        import wampli.cli
    except ImportError:
        import sys
        from os import path

        sys.path.append(path.abspath(path.join(__file__, "../..")))

        import wampli.cli

    wampli.cli.main()


if __name__ == "__main__":
    main()
