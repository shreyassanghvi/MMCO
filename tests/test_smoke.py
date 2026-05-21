def test_mmco_imports_and_exposes_version():
    import mmco

    assert isinstance(mmco.__version__, str)
    assert mmco.__version__  # non-empty
