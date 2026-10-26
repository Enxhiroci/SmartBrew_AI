# Task B enhancement — Customer dashboard, saved drinks and order history

The revised interface separates two actions after customization:

- **Save to My Dashboard (R07):** require customer login, ask for recipe name, save current beverage/configuration, and show it under My saved drinks. No order, payment, stock consumption, or transaction occurs.
- **Place as a new order (R03/R04):** open checkout and only create an order when simulated payment is approved. If logged in, the order is linked to the current customer and immediately becomes visible in My order history (R09). Guests may order, but the order is not automatically assigned to an account.

Saved drink actions: **Edit / rename** modifies name and customization of the saved recipe only; **Place as new order** loads its settings into checkout. Previous orders stay immutable.

History actions: **Order again** loads the historical drink and customization into a new checkout (without automatic payment).

Saved profile preferences prefill new menu drink choices when supported, while saved recipe or historical-order customizations take precedence when those are explicitly chosen. Recommendations use frequency of previously ordered drinks, without rewriting explicit preferences.

## Evidence and limitations

Automated API regression suite: 23 tests passed. Separate Chromium DOM smoke testing with mocked server responses verified the navigation and button interactions; full browser-to-live-server navigation was blocked in the execution environment, so that is not claimed as verified. Real coffee preparation and payment remain simulated.
