from src.app.resource_paths import data_dir
from src.app.version import APP_NAME, APP_VERSION, BUILD_STAGE


def main() -> None:
    data_dir().mkdir(parents=True, exist_ok=True)
    print(f"{APP_NAME} {APP_VERSION} ({BUILD_STAGE})")
    print(f"Local data: {data_dir()}")
    from run import run_companion

    run_companion()


if __name__ == "__main__":
    main()
