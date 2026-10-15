# Customer and administrator walkthrough

[Back to the project overview](../README.md).

You can be the ticket raiser and the administrator. Use **two tabs in the same browser profile** so they share your isolated demo workspace. Separate browsers or private windows create different sessions.

### 1. Start as the administrator

1. Open the [live administrator workspace](https://ai-ticket-triage-chi.vercel.app/).
2. Click **Try the demo**. The public demo credentials are `demo` / `try-triage`; no owner credentials are needed.
3. Open **Knowledge base**. The demo includes fictional support guidance and an urgency policy. If an empty demo offers **Load starter examples**, click it first.
4. Click **Rebuild index** and wait for it to finish. This prepares the articles for retrieval and consumes an embedding request.
5. Keep the admin tab open. Open **Customer portal** in a second tab in the same browser.

### 2. Raise an enquiry as the customer

1. In the [customer portal](https://ai-ticket-triage-chi.vercel.app/support), select **New enquiry**.
2. Enter a subject and one of the enquiries below, then click **Get help**.
3. Note the ticket number so you can find it in the admin tab.
4. For an automatic answer, expand **Sources behind this answer** to inspect its evidence. A review case displays **With support**.

**Expected automatic answer — general refund policy**

> After a refund has been approved, how long does it usually take to reach the original payment method? I only need the general policy, not an account lookup.

With the starter knowledge indexed, the answer should explain the documented five-to-ten-business-day timeframe and cite the Billing article.

**Expected automatic answer — technical reporting guidance**

> What information should I include when reporting a technical problem? I only need the documented checklist, not an investigation of my account.

The answer should give the reporting checklist from the starter guidance.

**Expected admin review — request a financial action**

> Please issue a refund for my most recent subscription payment.

**Expected admin review — account recovery**

> I lost my authenticator and cannot sign in. Please reset two-factor authentication on my account.

**Expected admin review — unsupported information**

> Exactly how many gigabytes of storage are included in the Enterprise plan?

The starter knowledge does not establish a storage allowance, so this should go to support instead of inventing a number. Provider errors, exhausted quotas, or a missing/stale index can also send a routine question to review.

### 3. Handle an enquiry as the administrator

1. Return to the admin tab and open **Needs review**. Refresh the page if a new enquiry has not appeared yet.
2. Open the ticket with the number you noted. Read the escalation explanation and expand **Customer conversation**.
3. In **Correction or revision instructions**, write the complete response you want the customer to receive.
4. Click **Publish correction**. This publishes your response and resolves the ticket as **Resolved by support**.
5. Return to the customer tab, open the same enquiry under **Recent enquiries**, and click **Refresh** to see your response.

The prototype records support replies; it does not execute refunds, reset accounts, or perform external actions. For those requests, explain the next support step rather than claiming an action was completed.

### 4. Review and change an already resolved ticket

1. Open **All tickets** in admin, filter for resolved tickets, and select the refund-policy enquiry from step 2. You can also use **Overview → Audit AI answers**.
2. Inspect the latest answer and the sources in **Customer conversation**. Click **Mark reviewed** to record that you checked an acceptable answer.
3. To change it, paste this complete replacement into **Correction or revision instructions**:

   > Approved refunds usually take five to ten business days to reach the original payment method. If more than ten business days have passed, our Billing team should investigate the refund reference.

4. Click **Publish correction**. Refresh the customer tab: the original answer remains visible, followed by the support team's **Updated answer**.
5. Expand **Audit trail** in admin to inspect the recorded review and correction.

For an AI-assisted edit, enter internal instructions such as “Make the answer shorter and retain the refund timeframe,” then click **Request AI changes**. Inspect the result marked **Draft · not visible to customer**, then click **Publish revised answer**. Revision instructions stay internal; **Publish correction** immediately publishes the text you entered.

To reopen a ticket yourself, enter a reason and click **Reopen for review**. To try the customer route, type under **Still need help?** and click **Send to support team**; the ticket returns to human review.

**Demo lifecycle:** the workspace expires after 30 minutes of inactivity. **End demo & delete data** removes its content; do this after your walkthrough. Keep the session active until you finish testing both roles. Use fictional, non-sensitive enquiries. The app displays the remaining AI allowance, and free-provider availability can vary.
