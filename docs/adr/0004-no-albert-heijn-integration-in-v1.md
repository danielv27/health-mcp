# No Albert Heijn integration in v1

The Catalog is seeded by hand. There is no Albert Heijn adapter, no product search, and
no automatic macro resolution.

The repertoire of food one person actually eats is small — a few dozen Products — and
each only needs resolving once. That makes a live supermarket integration a convenience
on a path walked a few times a month, not infrastructure. Albert Heijn's API is
reverse-engineered and unofficial, so paying for it with a token manager, a GS1 nutrient
parser, and a standing drift risk buys very little.

## Consequences

Adding a new Product costs a minute of typing off the label. If that becomes tiresome,
the integration is purely additive — nothing in the schema or the tools has to change to
accept a machine-resolved Product later.

## Preserved findings

Verified live on 2026-08-11, kept so the research isn't repeated from scratch:

- `product/search/v2` returns HTTP 500 (`ApplicationContextNotFoundException`) unless the
  request carries **`x-application: AHWEBSHOP`**. `APPIE`/`appie` both fail. The widely
  circulated public gist omits this and is now wrong.
- An anonymous token from `POST /mobile-auth/v1/auth/token/anonymous` with
  `{"clientId":"appie"}` is sufficient for search — no login. `expires_in` is 7199s.
- **Search returns no nutrition.** Macros need a second call to
  `GET /mobile-services/product/detail/v4/fir/{webshopId}`, where
  `tradeItem.nutritionalInformation.nutrientHeaders[0]` holds GS1-coded values against an
  explicit `nutrientBasisQuantity`. Codes seen: `ENER-` (emitted **twice**, kJ and kcal —
  discriminate on `measurementUnitCode`), `PRO-`, `CHOAVL`, `FAT`, `FASAT`, `SUGAR-`,
  `SALTEQ`. Product lookup is therefore inherently a two-call flow.
- `tradeItem.gtin` is the EAN, and `tradeItem.measurements.netContent` is the pack size.
