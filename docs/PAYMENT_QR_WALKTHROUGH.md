# SmartBrew AI — Payment and QR Receipt Demonstration (R04)

These are **educational software simulations**, not real payment transactions or fiscal invoices.

## Three payment methods

1. **Bank card**: Select Visa or Mastercard, use demo last four digits `4242`. The confirmation and receipt show only the brand and a masked suffix. Do not enter a real card number.
2. **Apple / Google Pay**: Choose the wallet provider and check **Authorize this demo wallet transaction**. No wallet SDK or device confirmation runs.
3. **Employee card**: Enter demo badge `EMP-1001` and test PIN `1357`. An incorrect PIN rejects the demo attempt. The PIN is not persisted or printed.

Choose **Declined payment (test)** to confirm the transaction is rejected before an order is created and before stock is consumed.

## Real scannable QR receipt

1. Choose **Receipt option → QR receipt preview**.
2. Confirm an approved demo payment.
3. The on-screen receipt displays a high-contrast QR and a **Download QR PNG** button.
4. Scan with a phone camera or QR scanner to read the receipt reference, UTC date, drink, total and simulation disclaimer **without requiring internet**.
5. Select **Download PDF receipt**; the same QR appears on the page with the itemized bill. The print link opens this PDF.

The QR does not contain private tracking tokens, payment credentials, employee PINs, or email addresses. It is a portable order-summary text, **not** an online receipt verification page.

## Expected checkout behavior

Saving a named beverage to **My Dashboard** does not place an order. Placing a new order goes through the above payment choice. Approved demo orders appear in a signed-in customer's **My order history**, including the non-sensitive payment label; a guest's order is not attached to another account. **Order another drink** returns to the menu without erasing previous orders.

## Testing

Run `python -m pytest -q` from the project root. The automated suite checks method-specific validation, masked payment information, protected QR images, one-page QR PDF rendering, order history, and the original functionality. A mocked-API browser smoke check verified payment form switching and QR preview markup; true browser-to-local-server navigation was blocked during authoring and should be verified on the student's local machine.
