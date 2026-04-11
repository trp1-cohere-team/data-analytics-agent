from utils.join_key_resolver import JoinKeyResolver


def test_normalize_customer_id_from_int() -> None:
    resolver = JoinKeyResolver()
    result = resolver.normalize_customer_id(123)
    assert result.normalized == "123"
    assert result.strategy == "int_to_string"


def test_normalize_customer_id_from_prefixed_string() -> None:
    resolver = JoinKeyResolver()
    result = resolver.normalize_customer_id("CUST-00123")
    assert result.normalized == "123"


def test_normalize_customer_id_from_padded_numeric_string() -> None:
    resolver = JoinKeyResolver()
    result = resolver.normalize_customer_id("000123")
    assert result.normalized == "123"


def test_normalize_product_code() -> None:
    resolver = JoinKeyResolver()
    result = resolver.normalize_product_code("prd_a12")
    assert result.normalized == "PRD_A12"


def test_keys_match_customer() -> None:
    resolver = JoinKeyResolver()
    assert resolver.keys_match(123, "CUST-00123", entity_type="customer") is True


def test_keys_match_product() -> None:
    resolver = JoinKeyResolver()
    assert resolver.keys_match("PRD_A12", "prd_a12", entity_type="product") is True
