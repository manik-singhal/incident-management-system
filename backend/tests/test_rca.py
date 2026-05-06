from main import is_valid_rca


def test_empty_rca():
    assert is_valid_rca("") == False


def test_spaces_only_rca():
    assert is_valid_rca("     ") == False


def test_valid_rca():
    assert is_valid_rca("Database connection failure") == True


print("All RCA tests passed")
