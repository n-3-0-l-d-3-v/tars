from __TARS_PACKAGE_NAME__.cli import greet


def test_greet_default_includes_project_name():
    assert "__TARS_PROJECT_NAME__" in greet("World")


def test_greet_includes_given_name():
    assert "Ada" in greet("Ada")
