# Join Key Resolver

Normalizes identifiers across heterogeneous systems.

## Supported cases

- Customer IDs:
  - `123`
  - `000123`
  - `CUST-00123`

- Product codes:
  - `PRD_A12`
  - `prd_a12`

- Order IDs:
  - `123`
  - `000123`

## Example

```python
from utils.join_key_resolver import JoinKeyResolver

resolver = JoinKeyResolver()
resolver.keys_match(123, "CUST-00123", entity_type="customer")
# True
