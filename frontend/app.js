/** SmartBrew AI kiosk controller. Backend is always the source of truth for prices and stock. */
const $ = (id) => document.getElementById(id);
const state = {
  page: 'discover', category: 'All', catalog: [], selectedId: null,
  authToken: sessionStorage.getItem('sb_auth') || '',
  adminToken: sessionStorage.getItem('sb_admin') || '',
  tracking: null, trackingInterval: null, registering: false, editingRecipeId: null, editingRecipeName: '',
  profilePreferences: null,
};

/** Escape untrusted server/user text before inserting into HTML. @param {unknown} v - text. @returns {string} safe HTML text. */
function escapeHtml(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
}

/** Issue same-origin JSON request and convert errors to messages. @param {string} path - endpoint. @param {object} options - fetch options. @param {string} token - optional bearer. @returns {Promise<any>} parsed JSON. */
async function api(path, options = {}, token = '') {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) } });
  const body = await response.json();
  if (!response.ok) throw Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`);
  return body;
}

/** Display brief feedback toast to the user. @param {string} message - user feedback. @param {boolean} error - error style flag. @returns {void} */
function toast(message, error = false) {
  const el = $('toast'); el.textContent = message; el.classList.toggle('error', error); el.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => { el.hidden = true; }, 4500);
}

/** Execute asynchronous UI task and report failures. @param {Function} fn - action callback. @returns {Promise<void>} completion. */
async function safely(fn) {
  try { await fn(); } catch (error) { toast(error.message || String(error), true); }
}

/** Close the customer account menu and synchronize its ARIA expanded state. @returns {void} */
function closeAccountMenu() {
  $('account-menu').hidden = true;
  $('identity').setAttribute('aria-expanded', 'false');
}

/** Update header accessibility as customer signs in or out. @param {string} name - account label. @returns {void} */
function setAccountIdentity(name) {
  $('identity').textContent = name;
  $('identity').setAttribute('aria-label', state.authToken ? `${name}: open account menu` : 'Guest session: sign in or create an account');
  closeAccountMenu();
}

/** Open the signed-in user menu, or take guests to customer login. @returns {void} */
function toggleAccountMenu() {
  if (!state.authToken) { closeAccountMenu(); showPage('profile'); return; }
  const menu = $('account-menu');
  menu.hidden = !menu.hidden;
  $('identity').setAttribute('aria-expanded', String(!menu.hidden));
  if (!menu.hidden) $('account-open-profile').focus();
}

/** Open the profile section and scroll to its relevant content. @param {string} sectionId - optional anchor ID. @returns {void} */
function openAccountSection(sectionId = '') {
  closeAccountMenu();
  showPage('profile');
  if (sectionId) {
    // Allow showPage to toggle visibility before moving focus to the destination.
    const target = $(sectionId);
    requestAnimationFrame(() => target?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }
}

/** Set visible tab and optionally load its data. @param {string} page - page ID. @returns {void} */
function showPage(page) {
  state.page = page;
  closeAccountMenu();
  document.querySelectorAll('.page').forEach(el => el.classList.toggle('active', el.id === page));
  document.querySelectorAll('.nav-btn').forEach(el => el.classList.toggle('active', el.dataset.page === page));
  if (page === 'profile') safely(refreshProfile);
  if (page === 'technician' && state.adminToken) safely(refreshAdmin);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

/** Fetch categorized menu and render current availability. @returns {Promise<void>} completion. */
async function refreshCatalog() {
  state.catalog = await api('/api/catalog');
  $('menu-count').textContent = `${state.catalog.length} curated beverages`;
  renderCatalog();
}

/** Render drinks for selected category, with sold-out states. @returns {void} */
function renderCatalog() {
  const list = state.catalog.filter(d => state.category === 'All' || d.category === state.category);
  $('drink-grid').innerHTML = list.map(d => `<article class="drink-card">
    <div class="drink-visual ${d.category === 'Tea' ? 'tea' : d.category === 'Cold drinks' ? 'cold' : ''}">${d.category === 'Tea' ? '🍵' : d.category === 'Cold drinks' ? '🧊' : '☕'}</div>
    <div class="drink-body"><div class="drink-cat">${escapeHtml(d.category)} · ${d.calories} kcal</div><h3 class="drink-name">${escapeHtml(d.name)}</h3>
    <p class="drink-desc">${escapeHtml(d.description)}</p><div class="drink-footer"><div><div class="price">€${d.price.toFixed(2)}</div><span class="calories">Starting price</span></div>
    ${d.available ? `<button class="small-btn select-drink" data-id="${d.id}">Customize ↗</button>` : '<span class="out-of-stock">Unavailable</span>'}</div></div></article>`).join('');
  document.querySelectorAll('.select-drink').forEach(btn => btn.addEventListener('click', () => safely(() => selectDrink(Number(btn.dataset.id)))));
}

/** Read customization widgets into an API payload. @returns {object} selected beverage settings. */
function chosenCustomization() {
  return { milk: $('milk').value, strength: $('strength').value, temperature: $('temperature').value,
    syrup: $('syrup').value, size: $('size').value };
}

/** Populate customizer for a beverage and request quote. @param {number} id - drink ID. @param {object|null} preset - saved recipe options. @param {number|null} editingRecipeId - optional recipe being edited. @param {string} editingRecipeName - current recipe name. @returns {Promise<void>} completion. */
async function selectDrink(id, preset = null, editingRecipeId = null, editingRecipeName = '') {
  const drink = state.catalog.find(d => d.id === id);
  if (!drink) throw Error('Beverage not available');
  // Selecting a drink after checkout starts a fresh checkout without deleting that order.
  if (state.tracking) resetCheckoutState();
  state.selectedId = id;
  state.editingRecipeId = editingRecipeId;
  state.editingRecipeName = editingRecipeName;
  $('edit-recipe-panel').hidden = editingRecipeId === null;
  $('custom-flow-choice').hidden = editingRecipeId !== null;
  $('save-recipe-panel').hidden = true;
  $('checkout-section').hidden = true;
  if (editingRecipeId !== null) $('edit-recipe-name').value = editingRecipeName;
  $('selected-drink-title').textContent = drink.name;
  $('temperature').innerHTML = drink.supported_temperatures.map(t => `<option value="${t}">${t[0].toUpperCase()}${t.slice(1)}</option>`).join('');
  for (const [id, value] of Object.entries({milk:'dairy', strength:'regular', syrup:'none', size:'medium'})) $(id).value = value;
  // New menu choices start with the customer's saved defaults; a selected recipe takes precedence.
  const settings = preset || (state.authToken && state.profilePreferences ? {
    milk:state.profilePreferences.milk_type, strength:state.profilePreferences.coffee_strength,
    temperature:state.profilePreferences.temperature, syrup:state.profilePreferences.syrup_preference,
  } : null);
  if (settings) Object.entries(settings).forEach(([key, val]) => {
    if ($(key) && [...$(key).options].some(option => option.value === val)) $(key).value = val;
  });
  $('order-panel').hidden = false;
  await refreshQuote();
  $('order-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/** Show the explicit save-to-dashboard option or ask the customer to sign in. @returns {void} */
function chooseSaveFlow() {
  if (!state.authToken) {
    showPage('profile');
    toast('Please sign in or create an account, then return to your customized drink to save it.');
    return;
  }
  $('save-recipe-panel').hidden = false;
  $('checkout-section').hidden = true;
  $('edit-recipe-panel').hidden = true;
  $('custom-recipe-name').focus();
}

/** Open checkout for a configured beverage, without charging or placing an order yet. @returns {void} */
function chooseOrderFlow() {
  if (!state.selectedId) throw Error('Choose a drink first');
  $('checkout-section').hidden = false;
  $('checkout-account-note').textContent = state.authToken
    ? 'You are signed in. This purchase will appear under My Dashboard → My order history after the simulated payment is approved.'
    : 'Guest checkout: this order can be tracked with its receipt, but it will NOT be added to a registered customer’s history. Sign in before ordering to save it in your dashboard.';
  $('save-recipe-panel').hidden = true;
  $('edit-recipe-panel').hidden = true;
  $('checkout-section').scrollIntoView({behavior:'smooth', block:'start'});
}

/** Get validated price and ingredient check for current customization. @returns {Promise<void>} completion. */
async function refreshQuote() {
  if (!state.selectedId) return;
  const quote = await api('/api/quote', { method: 'POST', body: JSON.stringify({ beverage_id: state.selectedId, customization: chosenCustomization() }) });
  $('quote-details').textContent = quote.available
    ? `Your price: €${quote.price.toFixed(2)} · Available to prepare. All options will be included in your order.`
    : `Unavailable: ${quote.blocking_reasons.join('; ')}`;
  $('place-order').disabled = !quote.available;
}

/** Present specific simulated payment controls and explanations. @returns {void} */
function updatePaymentChoice() {
  const method = $('payment-method').value;
  $('bank-card-fields').hidden = method !== 'bank_card';
  $('wallet-fields').hidden = method !== 'mobile_wallet';
  $('employee-fields').hidden = method !== 'employee_card';
  const descriptions = {
    bank_card: ['Bank card · demonstration', 'Select Visa or Mastercard and a four-digit demo suffix. SmartBrew never collects a full payment card number.'],
    mobile_wallet: ['Apple Pay / Google Pay · demonstration', 'Select the simulated wallet provider and explicitly confirm the test transaction. No device payment sheet or wallet API is opened.'],
    employee_card: ['Employee card · demonstration', 'Use sample card EMP-1001 and test PIN 1357. No real employee account or balance is accessed.'],
  };
  $('payment-details-title').textContent = descriptions[method][0];
  $('payment-details-description').textContent = descriptions[method][1];
}

/** Collect demo-only payment metadata for backend validation. @returns {object} payment metadata. */
function paymentDetails() {
  const method = $('payment-method').value;
  if (method === 'bank_card') {
    const last4 = $('bank-card-last4').value.trim();
    if (!/^[0-9]{4}$/.test(last4)) throw Error('Enter exactly 4 DEMO card digits (e.g. 4242)');
    return {brand: $('bank-card-brand').value, last4};
  }
  if (method === 'mobile_wallet') {
    if (!$('wallet-confirm').checked) throw Error('Confirm the simulated wallet transaction');
    return {wallet: $('wallet-provider').value, confirmed: 'yes'};
  }
  const badge = $('employee-badge').value.trim();
  if (!/^[A-Za-z0-9-]{4,16}$/.test(badge)) throw Error('Enter a valid demo employee ID');
  if ($('employee-demo-pin').value !== '1357') throw Error('Enter demo employee PIN 1357');
  return {badge, demo_pin: $('employee-demo-pin').value};
}

/** Show email address input only for an emailed receipt. @returns {void} */
function updateReceiptChoice() {
  const byEmail = ['email', 'email_preview'].includes($('receipt-method').value);
  $('receipt-email-wrap').hidden = !byEmail;
  $('receipt-email').required = byEmail;
  $('receipt-email-label').textContent = $('receipt-method').value === 'email_preview' ? 'Recipient (preview only)' : 'Send receipt to email';
  $('qr-choice-note').hidden = $('receipt-method').value !== 'qr';
  $('receipt-email-note').textContent = $('receipt-method').value === 'email_preview'
    ? 'Safe demonstration: your address is displayed in the email preview, but no message is sent or queued.'
    : 'Real email is attempted only when SMTP is configured. Payments are simulated.';
}

/** Render a complete, escaped receipt with delivery state and simulation disclaimer. @param {object} receipt - backend receipt. @returns {void} */
function renderReceipt(receipt) {
  const receiptKey = JSON.stringify(receipt);
  if ($('receipt-preview').dataset.receiptKey === receiptKey) return;
  $('receipt-preview').dataset.receiptKey = receiptKey;
  const fields = receipt.customization || {};
  const labels = {milk:'Milk',strength:'Strength',temperature:'Temperature',syrup:'Syrup',size:'Size'};
  const detailRows = Object.entries(labels).map(([key, label]) => `<div class="receipt-line"><span>${label}</span><strong>${escapeHtml(fields[key] || '—')}</strong></div>`).join('');
  const date = new Date(receipt.created_at).toLocaleString();
  const email = ['email', 'email_preview'].includes(receipt.method) ? `<div class="receipt-line"><span>Email recipient</span><strong>${escapeHtml(receipt.email_to)}</strong></div>` : '';
  const qrMarkup = receipt.method === 'qr' && state.tracking
    ? `<div class="qr-receipt"><div class="qr-receipt-title">YOUR SCANNABLE QR RECEIPT</div><img src="/api/orders/${encodeURIComponent(state.tracking.id)}/receipt-qr.png?tracking_token=${encodeURIComponent(state.tracking.token)}" alt="Scannable QR with SmartBrew demo receipt summary" width="220" height="220"/><p>Scan to read the offline order summary · No account or payment credentials included</p></div>`
    : '';
  const emailHeader = receipt.method === 'email_preview' ? `<div class="email-preview-label">EMAIL PREVIEW · NOT SENT</div>
    <div class="email-preview-meta"><div><b>From:</b> SmartBrew AI &lt;noreply@smartbrew.example&gt; (sample)</div>
    <div><b>To:</b> ${escapeHtml(receipt.email_to)}</div>
    <div><b>Subject:</b> Your SmartBrew order receipt ${escapeHtml(receipt.reference)}</div></div>
    <p class="email-preview-greeting">Thank you for your SmartBrew order! Here is a summary of your simulated purchase.</p>` : '';
  $('receipt-preview').innerHTML = `${emailHeader}<div class="receipt-heading"><div><p class="overline green">SMARTBREW AI / RECEIPT</p><h3>${escapeHtml(receipt.reference)}</h3></div><img class="receipt-mark" src="/assets/smartbrew-logo.png?v=11" alt="SmartBrew AI brewing logo" width="64" height="60" /></div>
    <div class="receipt-line"><span>Timestamp</span><strong>${escapeHtml(date)}</strong></div>
    <div class="receipt-line"><span>Beverage</span><strong>${escapeHtml(receipt.drink)}</strong></div>
    ${detailRows}<div class="receipt-line"><span>Payment method</span><strong>${escapeHtml((receipt.payment_method || '').replaceAll('_',' '))}</strong></div>
    <div class="receipt-line"><span>Payment details</span><strong>${escapeHtml(receipt.payment_description || 'Simulated transaction')}</strong></div>
    <div class="receipt-line"><span>Payment status</span><strong>Approved · simulation</strong></div>
    ${email}<div class="receipt-line receipt-total"><span>Total</span><strong>€${Number(receipt.amount).toFixed(2)}</strong></div>
    ${qrMarkup}<p class="receipt-disclaimer">Demonstration only: payment and brewing are simulated. This is not a tax invoice; VAT is not calculated.</p>`;
  $('receipt-info').textContent = receipt.message || '';
  if (state.tracking) {
    const {id, token} = state.tracking;
    const path = `/api/orders/${id}/receipt.pdf?tracking_token=${encodeURIComponent(token)}`;
    $('download-receipt').href = path;
    $('download-receipt').download = `${receipt.reference}.pdf`;
    $('print-receipt').href = `${path}&inline=true`;
    $('download-qr').hidden = receipt.method !== 'qr';
    if (receipt.method === 'qr') {
      $('download-qr').href = `/api/orders/${id}/receipt-qr.png?tracking_token=${encodeURIComponent(token)}`;
      $('download-qr').download = `${receipt.reference}-QR.png`;
    }
  }
  $('retry-email').hidden = !(receipt.method === 'email' && ['failed', 'not_configured'].includes(receipt.email_status) && receipt.email_attempts < 3);
}

/** Apply server order status to progress and accessible status label. @param {object} data - order details. @returns {void} */
function renderTracking(data) {
  const steps = ['queued','brewing','ready'];
  const status = data.status;
  document.querySelectorAll('.step').forEach(el => el.classList.toggle('done', steps.indexOf(el.dataset.status) <= steps.indexOf(status)));
  $('order-status-chip').textContent = status[0].toUpperCase() + status.slice(1);
  $('order-progress').style.width = `${status === 'ready' ? 100 : status === 'brewing' ? 58 : 12}%`;
  $('order-message').textContent = status === 'ready' ? 'Your beverage is ready! (Simulation complete.)' :
    status === 'brewing' ? 'Your beverage is being prepared automatically…' : 'Payment approved in simulator. Your beverage is in the queue…';
}

/** Refresh active order from the server; update preview and stop polling when ready. @returns {Promise<void>} completion. */
async function pollTracking() {
  if (!state.tracking) return;
  const {id, token} = state.tracking;
  const data = await api(`/api/orders/${id}?tracking_token=${encodeURIComponent(token)}`);
  $('tracking-panel').hidden = false;
  $('order-number').textContent = `#${id}`;
  renderTracking(data);
  renderReceipt(data.receipt);
  if (data.status === 'ready' && state.trackingInterval) {
    clearInterval(state.trackingInterval);
    state.trackingInterval = null;
  }
}

/** Start background UI polling, resetting any previous interval. @returns {void} */
function beginTracking() {
  if (state.trackingInterval) clearInterval(state.trackingInterval);
  state.trackingInterval = setInterval(() => safely(pollTracking), 1200);
}

/** Place simulated paid order, optionally deliver real SMTP receipt and automatically track preparation. @returns {Promise<void>} completion. */
async function placeOrder() {
  if (!state.selectedId) throw Error('Select a beverage first');
  const emailSelected = ['email', 'email_preview'].includes($('receipt-method').value);
  const recipient = $('receipt-email').value.trim();
  if (emailSelected && (!recipient || !$('receipt-email').checkValidity())) throw Error('Enter a valid recipient email address');
  $('place-order').disabled = true;
  try {
    const result = await api('/api/orders', { method: 'POST', body: JSON.stringify({
      beverage_id: state.selectedId, customization: chosenCustomization(),
      payment_method: $('payment-method').value, payment_details: paymentDetails(), receipt_method: $('receipt-method').value,
      receipt_email: emailSelected ? recipient : null,
      payment_approved: $('payment-outcome').value === 'approve',
    }) }, state.authToken);
    state.tracking = {id: result.id, token: result.tracking_token};
    sessionStorage.setItem('sb_tracking', JSON.stringify(state.tracking));
    $('tracking-panel').hidden = false;
    $('order-panel').hidden = true;
    $('order-number').textContent = `#${result.id}`;
    renderTracking(result);
    renderReceipt(result.receipt);
    beginTracking();
    await refreshCatalog();
    if (state.authToken) await safely(refreshProfile);
    $('tracking-panel').scrollIntoView({ behavior:'smooth', block:'start' });
    toast(result.receipt.email_status === 'sent' ? 'Order placed; email accepted by SMTP provider.' :
      result.receipt.method === 'email_preview' ? 'Order placed. Email preview created — nothing sent.' :
      'Order placed! Preparation progresses automatically.');
  } finally {
    $('place-order').disabled = false;
  }
}

/** Retry sending an unsent receipt to the original recipient, without recreating the order. @returns {Promise<void>} completion. */
async function retryReceiptEmail() {
  if (!state.tracking) throw Error('No order to send a receipt for');
  const {id, token} = state.tracking;
  const result = await api(`/api/orders/${id}/email-receipt?tracking_token=${encodeURIComponent(token)}`, {method:'POST'});
  renderReceipt(result.receipt);
  toast(result.receipt.message, result.receipt.email_status !== 'sent');
}

/** Release only checkout state, preserving prior orders and accounts. @returns {void} */
function resetCheckoutState() {
  if (state.trackingInterval) clearInterval(state.trackingInterval);
  state.trackingInterval = null;
  state.tracking = null;
  sessionStorage.removeItem('sb_tracking');
  state.selectedId = null;
  state.editingRecipeId = null;
  state.editingRecipeName = '';
  $('order-panel').hidden = true;
  $('tracking-panel').hidden = true;
  $('edit-recipe-panel').hidden = true;
  $('save-recipe-panel').hidden = true;
  $('checkout-section').hidden = true;
  $('employee-demo-pin').value = '';
  $('wallet-confirm').checked = false;
  $('receipt-email').value = '';
  $('custom-recipe-name').value = '';
  $('edit-recipe-name').value = '';
  $('checkout-section').hidden = true;
  $('custom-flow-choice').hidden = false;
  $('save-recipe-panel').hidden = true;
  $('edit-recipe-panel').hidden = true;
  for (const [id, choice] of Object.entries({
    milk:'dairy', strength:'regular', temperature:'hot', syrup:'none', size:'medium',
    'payment-method':'bank_card', 'receipt-method':'qr', 'payment-outcome':'approve',
  })) {
    // Only set options that exist; the temperature choices depend on the beverage.
    if ([...$(id).options].some(option => option.value === choice)) $(id).value = choice;
  }
  updateReceiptChoice();
  updatePaymentChoice();
  $('place-order').disabled = false;
}

/** Begin a completely new customer order without erasing the completed order; return Promise<void>. */
async function startNewOrder() {
  resetCheckoutState();
  state.category = 'All';
  document.querySelectorAll('.filter[data-category]').forEach(el =>
    el.classList.toggle('active', el.dataset.category === 'All'));
  showPage('discover');
  await refreshCatalog();
  $('menu-heading').scrollIntoView({behavior:'smooth', block:'start'});
  toast('Ready for your next drink. Select a beverage from the menu.');
}

/** Request and render explainable locally-scored recommendations. @returns {Promise<void>} completion. */
async function findRecommendations() {
  const results = await api('/api/recommendations', { method: 'POST', body: JSON.stringify({
    weather: $('weather').value, mood: $('mood').value, time_available_minutes: Number($('time-available').value),
  }) }, state.authToken);
  $('recommendations').innerHTML = results.recommendations.length ? results.recommendations.map((r, idx) =>
    `<article class="recommendation"><span class="rank">CURATED MATCH 0${idx + 1}</span><h3>${escapeHtml(r.name)}</h3>
     <p class="rec-headline">${escapeHtml(r.headline)}</p>
     <p class="rec-story">${escapeHtml(r.description)}</p>
     <div class="rec-factors" aria-label="Why this drink was suggested">${r.reasons.map(reason => `<span class="rec-factor">${escapeHtml(reason)}</span>`).join('')}</div>
     <button class="small-btn recommendation-order" data-id="${r.id}">Make it yours ↗</button></article>`).join('') : '<p>No drinks available until maintenance restores service.</p>';
  document.querySelectorAll('.recommendation-order').forEach(el => el.addEventListener('click', () => safely(async () => {
    showPage('discover'); await selectDrink(Number(el.dataset.id));
  })));
}

/** Toggle sign-in and sign-up form states. @param {boolean} registering - whether to register. @returns {void} */
function setRegistering(registering) {
  state.registering = registering;
  $('name-wrap').hidden = !registering;
  $('show-login').classList.toggle('active', !registering);
  $('show-register').classList.toggle('active', registering);
  $('submit-auth').textContent = registering ? 'Create account' : 'Log in';
}

/** Authenticate or register a customer and open preferences. @returns {Promise<void>} completion. */
async function authenticate() {
  const payload = { email: $('auth-email').value, password: $('auth-password').value };
  if (state.registering) payload.name = $('register-name').value;
  const result = await api(state.registering ? '/api/register' : '/api/login', { method: 'POST', body: JSON.stringify(payload) });
  state.authToken = result.token; sessionStorage.setItem('sb_auth', result.token);
  await refreshProfile(); toast(`Signed in as ${result.name}`);
}

/** Load customer preferences and recipes if signed in. @returns {Promise<void>} completion. */
async function refreshProfile() {
  if (!state.authToken) { $('auth-panel').hidden = false; $('account-panel').hidden = true; setAccountIdentity('Guest session'); return; }
  try {
    const result = await api('/api/me', {}, state.authToken);
    setAccountIdentity(result.name);
    $('account-welcome').textContent = `Welcome back, ${result.name}`;
    $('pref-milk').value = result.preferences.milk_type;
    $('pref-strength').value = result.preferences.coffee_strength;
    $('pref-temperature').value = result.preferences.temperature;
    $('pref-syrup').value = result.preferences.syrup_preference;
    state.profilePreferences = result.preferences;
    $('auth-panel').hidden = true; $('account-panel').hidden = false;
    await Promise.all([refreshRecipes(), refreshOrderHistory()]);
  } catch (error) {
    state.authToken = ''; state.profilePreferences = null; sessionStorage.removeItem('sb_auth');
    $('auth-panel').hidden = false; $('account-panel').hidden = true;
    setAccountIdentity('Guest session'); throw error;
  }
}

/** Save logged-in user's beverage preferences. @returns {Promise<void>} completion. */
async function savePreferences() {
  await api('/api/preferences', { method: 'PUT', body: JSON.stringify({
    milk_type: $('pref-milk').value, coffee_strength: $('pref-strength').value,
    temperature: $('pref-temperature').value, syrup_preference: $('pref-syrup').value,
  }) }, state.authToken);
  state.profilePreferences = {milk_type:$('pref-milk').value, coffee_strength:$('pref-strength').value,
    temperature:$('pref-temperature').value, syrup_preference:$('pref-syrup').value};
  toast('Preferences saved. These will be preselected when you customize a new drink.');
}

/** Save the currently customized drink under a name; return to the dashboard (R07). @returns {Promise<void>} completion. */
async function saveRecipe() {
  if (!state.authToken) throw Error('Sign in before saving a recipe');
  if (!state.selectedId) throw Error('Select and customize a beverage first');
  const name = $('custom-recipe-name').value.trim();
  if (!name || name.length > 60) throw Error('Enter a recipe name (1–60 characters)');
  await api('/api/recipes', { method: 'POST', body: JSON.stringify({
    name, beverage_id: state.selectedId, customization: chosenCustomization(),
  }) }, state.authToken);
  $('custom-recipe-name').value = '';
  await refreshRecipes();
  showPage('profile');
  toast(`Saved "${name}" in your dashboard. No order was placed.`);
}

/** Save edited settings and name for a recipe owned by the current customer (R07). @returns {Promise<void>} completion. */
async function updateRecipe() {
  if (!state.editingRecipeId || !state.authToken) throw Error('Select a saved recipe to edit first');
  const name = $('edit-recipe-name').value.trim();
  if (!name || name.length > 60) throw Error('Enter a recipe name (1–60 characters)');
  const result = await api(`/api/recipes/${state.editingRecipeId}`, {method:'PUT', body: JSON.stringify({
    name, beverage_id: state.selectedId, customization: chosenCustomization(),
  })}, state.authToken);
  state.editingRecipeId = null;
  state.editingRecipeName = '';
  $('edit-recipe-panel').hidden = true;
  await refreshRecipes();
  showPage('profile');
  toast(`Updated "${result.name}". Your existing orders were not changed.`);
}

/** Display named recipes with distinct edit/rename and new-checkout actions (R07/R08). @returns {Promise<void>} completion. */
async function refreshRecipes() {
  const recipes = await api('/api/recipes', {}, state.authToken);
  $('recipe-list').innerHTML = recipes.length ? recipes.map(r => {
    const detail = Object.entries(r.customization).map(([key, value]) => `${key}: ${value}`).join(' · ');
    return `<article class="dashboard-item"><div><strong>${escapeHtml(r.name)}</strong><p>${escapeHtml(r.drink)}</p><small>${escapeHtml(detail)}</small></div>
      <div class="recipe-actions"><button class="outline edit-recipe" data-id="${r.id}" type="button">Edit / rename</button>
      <button class="primary order-recipe" data-id="${r.id}" type="button">Place as new order →</button></div></article>`;
  }).join('') : '<p class="muted">No saved drinks yet. Customize one and choose “Save to My Dashboard.”</p>';
  document.querySelectorAll('.order-recipe').forEach(el => el.addEventListener('click', () => safely(async () => {
    const recipe = recipes.find(r => r.id === Number(el.dataset.id));
    if (!recipe) throw Error('Saved recipe not found');
    await refreshCatalog(); showPage('discover');
    await selectDrink(recipe.beverage_id, recipe.customization);
    chooseOrderFlow();
    toast(`Loaded "${recipe.name}" for a NEW checkout; payment has not been submitted.`);
  })));
  document.querySelectorAll('.edit-recipe').forEach(el => el.addEventListener('click', () => safely(async () => {
    const recipe = recipes.find(r => r.id === Number(el.dataset.id));
    if (!recipe) throw Error('Saved recipe not found');
    await refreshCatalog(); showPage('discover');
    await selectDrink(recipe.beverage_id, recipe.customization, recipe.id, recipe.name);
    toast('Change the name or options, then choose Save recipe changes.');
  })));
}

/** Load a signed-in customer's purchase history and provide another-checkout links (R09). @returns {Promise<void>} completion. */
async function refreshOrderHistory() {
  if (!state.authToken) { $('order-history').innerHTML = ''; return; }
  const orders = await api('/api/my/orders', {}, state.authToken);
  $('order-history').innerHTML = orders.length ? orders.map(o => {
    const options = Object.entries(o.customization).map(([key, value]) => `${key}: ${value}`).join(' · ');
    return `<article class="dashboard-item"><div><strong>${escapeHtml(o.reference)} · ${escapeHtml(o.drink)}</strong>
      <p>${escapeHtml(new Date(o.created_at).toLocaleString())} · €${o.price.toFixed(2)} · ${escapeHtml(o.status)}</p>
      <small>${escapeHtml(options)}</small><small>Payment: ${escapeHtml(o.payment_description || o.payment_method)} · ${escapeHtml(o.payment_status)}</small></div><button class="outline repeat-history" type="button" data-id="${o.id}">Order again →</button></article>`;
  }).join('') : '<p class="muted">No completed purchases for this account. Signed-in orders will appear here automatically.</p>';
  document.querySelectorAll('.repeat-history').forEach(el => el.addEventListener('click', () => safely(async () => {
    const order = orders.find(o => o.id === Number(el.dataset.id));
    if (!order) throw Error('Order no longer available');
    await refreshCatalog(); showPage('discover');
    await selectDrink(order.beverage_id, order.customization);
    chooseOrderFlow();
    toast(`Loaded ${order.reference} settings into a NEW checkout. Previous order remains unchanged.`);
  })));
}

/** Log out of the customer session on this browser tab. @returns {void} */
function logout() {
  state.authToken = ''; state.profilePreferences = null; sessionStorage.removeItem('sb_auth');
  $('auth-panel').hidden = false; $('account-panel').hidden = true;
  setAccountIdentity('Guest session'); $('order-history').innerHTML = ''; $('recipe-list').innerHTML = ''; toast('Signed out of the kiosk.');
}

/** Authenticate technician with protected PIN and load console. @returns {Promise<void>} completion. */
async function adminLogin() {
  const data = await api('/api/admin/login', { method: 'POST', body: JSON.stringify({ pin: $('admin-pin').value }) });
  state.adminToken = data.token; sessionStorage.setItem('sb_admin', data.token);
  $('admin-pin').value = ''; await refreshAdmin(); toast('Technician mode unlocked.');
}

/** Render full technician maintenance dashboard and recent events. @returns {Promise<void>} completion. */
async function refreshAdmin() {
  if (!state.adminToken) { $('admin-auth').hidden = false; $('admin-console').hidden = true; return; }
  const [status, events] = await Promise.all([api('/api/admin/status', {}, state.adminToken), api('/api/admin/events', {}, state.adminToken)]);
  $('admin-auth').hidden = true; $('admin-console').hidden = false;
  $('admin-stats').innerHTML = `<div class="stat"><small>Active faults</small><b>${status.faults.length}</b></div><div class="stat"><small>Waste level</small><b>${status.waste.bin_level}%</b></div><div class="stat"><small>Active alerts</small><b>${status.alerts.length}</b></div>`;
  $('ingredient-list').innerHTML = status.ingredients.map(r => `<div class="stock-row ${r.quantity <= r.threshold ? 'low' : ''}"><div><strong>${escapeHtml(r.name.replaceAll('_',' '))}</strong> <span>${r.quantity} ${escapeHtml(r.unit)} · low alert at ${r.threshold}</span></div><button class="outline refill" data-name="${escapeHtml(r.name)}">+ Refill</button></div>`).join('');
  document.querySelectorAll('.refill').forEach(el => el.addEventListener('click', () => safely(() => refillIngredient(el.dataset.name))));
  $('waste-detail').textContent = `${status.waste.bin_level}% of ${status.waste.bin_capacity}% waste capacity used.`;
  $('fault-list').innerHTML = status.faults.length ? status.faults.map(f => `<div class="fault-row"><span class="error-text">⚠ ${escapeHtml(f.message)}</span><button class="outline resolve-fault" data-id="${f.id}">Resolve</button></div>`).join('') : '<p class="muted">No active machine faults.</p>';
  document.querySelectorAll('.resolve-fault').forEach(el => el.addEventListener('click', () => safely(async () => {
    await api(`/api/admin/faults/${el.dataset.id}/resolve`, { method: 'POST' }, state.adminToken);
    await refreshAdmin(); await refreshCatalog(); toast('Fault resolved.');
  })));
  $('event-list').innerHTML = events.map(e => `<div class="event-row"><strong>${escapeHtml(e.event)}</strong><span>${escapeHtml(e.detail)} · ${new Date(e.created_at*1000).toLocaleTimeString()}</span></div>`).join('');
}

/** Prompt for refill quantity and commit technician inventory update. @param {string} name - ingredient key. @returns {Promise<void>} completion. */
async function refillIngredient(name) {
  const value = window.prompt(`Refill ${name}: add how many units?`, '500');
  if (value === null) return;
  const amount = Number(value);
  if (!Number.isInteger(amount) || amount < 1) throw Error('Enter a positive whole-number quantity');
  await api(`/api/admin/ingredients/${encodeURIComponent(name)}/refill`, { method: 'POST', body: JSON.stringify({ amount }) }, state.adminToken);
  await refreshAdmin(); await refreshCatalog(); toast(`Refilled ${name} (+${amount}).`);
}

/** Simulate waste growth for maintenance tests. @returns {Promise<void>} completion. */
async function simulateWaste() {
  await api('/api/admin/bin/fill', { method: 'POST', body: JSON.stringify({ amount: 25 }) }, state.adminToken);
  await refreshAdmin(); await refreshCatalog(); toast('Waste level increased by 25% in simulator.');
}

/** Empty simulated waste bin with technician rights. @returns {Promise<void>} completion. */
async function emptyWaste() {
  await api('/api/admin/bin/empty', { method: 'POST' }, state.adminToken);
  await refreshAdmin(); await refreshCatalog(); toast('Waste bin counter reset.');
}

/** Insert a simulated hardware fault for safety monitoring demo. @returns {Promise<void>} completion. */
async function injectFault() {
  await api('/api/admin/faults', { method: 'POST', body: JSON.stringify({ message: $('fault-description').value }) }, state.adminToken);
  $('fault-description').value = ''; await refreshAdmin(); await refreshCatalog(); toast('Fault injected: kiosk ordering is blocked.');
}

/** Lock technician console and drop admin token from this browser tab. @returns {void} */
function adminLogout() {
  state.adminToken = ''; sessionStorage.removeItem('sb_admin');
  $('admin-console').hidden = true; $('admin-auth').hidden = false; toast('Technician console locked.');
}

/** Bind controls and fetch initial stock-aware menu. @returns {Promise<void>} completion. */
async function initialize() {
  document.querySelectorAll('.nav-btn').forEach(btn => btn.addEventListener('click', () => showPage(btn.dataset.page)));
  $('identity').addEventListener('click', toggleAccountMenu);
  $('account-open-profile').addEventListener('click', () => openAccountSection());
  $('account-open-recipes').addEventListener('click', () => openAccountSection('recipe-list'));
  $('account-open-history').addEventListener('click', () => openAccountSection('order-history'));
  $('account-menu-logout').addEventListener('click', () => { closeAccountMenu(); logout(); showPage('profile'); });
  document.addEventListener('click', (event) => { if (!$('account-nav').contains(event.target)) closeAccountMenu(); });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !$('account-menu').hidden) { closeAccountMenu(); $('identity').focus(); }
  });

  document.querySelectorAll('.filter[data-category]').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('.filter[data-category]').forEach(el => el.classList.remove('active'));
    btn.classList.add('active'); state.category = btn.dataset.category; renderCatalog();
  }));
  $('explore-btn').addEventListener('click', () => $('menu-heading').scrollIntoView({ behavior: 'smooth' }));
  $('close-customizer').addEventListener('click', () => { $('order-panel').hidden = true; });
  for (const id of ['milk','strength','temperature','syrup','size']) $(id).addEventListener('change', () => safely(refreshQuote));
  $('place-order').addEventListener('click', () => safely(placeOrder));
  $('update-recipe').addEventListener('click', () => safely(updateRecipe));
  $('choose-save').addEventListener('click', chooseSaveFlow);
  $('choose-order').addEventListener('click', chooseOrderFlow);
  $('confirm-save-recipe').addEventListener('click', () => safely(saveRecipe));
  $('cancel-save-recipe').addEventListener('click', () => { $('save-recipe-panel').hidden = true; });
  $('cancel-edit-recipe').addEventListener('click', () => { $('edit-recipe-panel').hidden = true; state.editingRecipeId = null; showPage('profile'); });
  $('back-to-customize').addEventListener('click', () => { $('checkout-section').hidden = true; });
  $('receipt-method').addEventListener('change', updateReceiptChoice);
  $('payment-method').addEventListener('change', updatePaymentChoice);
  $('retry-email').addEventListener('click', () => safely(retryReceiptEmail));
  $('new-order').addEventListener('click', () => safely(startNewOrder));
  updateReceiptChoice();
  updatePaymentChoice();
  $('get-recs').addEventListener('click', () => safely(findRecommendations));
  $('show-login').addEventListener('click', () => setRegistering(false));
  $('show-register').addEventListener('click', () => setRegistering(true));
  $('submit-auth').addEventListener('click', () => safely(authenticate));
  $('save-preferences').addEventListener('click', () => safely(savePreferences));
  $('new-drink-for-recipe').addEventListener('click', () => safely(startNewOrder));
  $('refresh-orders').addEventListener('click', () => safely(refreshOrderHistory));
  $('logout').addEventListener('click', logout);
  $('admin-login').addEventListener('click', () => safely(adminLogin));
  $('refresh-admin').addEventListener('click', () => safely(refreshAdmin));
  $('fill-bin').addEventListener('click', () => safely(simulateWaste));
  $('empty-bin').addEventListener('click', () => safely(emptyWaste));
  $('create-fault').addEventListener('click', () => safely(injectFault));
  $('admin-logout').addEventListener('click', adminLogout);
  await refreshCatalog();
  if (state.authToken) await safely(refreshProfile);
  try {
    state.tracking = JSON.parse(sessionStorage.getItem('sb_tracking') || 'null');
    if (state.tracking?.id && state.tracking?.token) {
      await pollTracking();
      if (state.trackingInterval === null && $('order-status-chip').textContent !== 'Ready') beginTracking();
    }
  } catch (_) { state.tracking = null; sessionStorage.removeItem('sb_tracking'); }
}

safely(initialize);
