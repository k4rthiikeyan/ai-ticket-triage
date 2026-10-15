import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const base = process.argv[2];
assert(base && new URL(base).protocol === 'https:');
const browser = await chromium.launch({headless:true});
const context = await browser.newContext({viewport:{width:1440,height:1000}});
const page = await context.newPage();
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
const report={mode:'live_deployed_browser',passed:false,checks:{}};
const output=resolve('artifacts');
await mkdir(output,{recursive:true});
let signedIn=false;
try {
  await page.goto(base,{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Try the demo',exact:true}).click();
  await page.getByRole('heading',{name:'More answers. Fewer handoffs.',exact:true}).waitFor();
  signedIn=true;
  await page.getByRole('link',{name:'Customer portal',exact:true}).click();
  await page.getByLabel('Subject',{exact:true}).fill('Live browser verification — human assistance');
  await page.getByLabel('Your enquiry',{exact:true}).fill('Please connect me to a human agent for this fictional browser verification.');
  const response=page.waitForResponse(r=>r.url().endsWith('/api/portal/tickets')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Get help',exact:true}).click();
  const result=await (await response).json();
  assert.equal(result.ticket.resolution_state,'needs_review');
  await page.getByText('Our support team is reviewing your enquiry.',{exact:true}).waitFor();
  report.checks.customer_submission_and_handoff=true;
  await page.getByRole('link',{name:'Admin workspace',exact:true}).click();
  await page.goto(base+'/tickets/'+result.ticket.id);
  await page.getByLabel('Correction or revision instructions').fill('Your fictional browser-verification enquiry has been reviewed by the support team. No account action was needed.');
  await page.getByRole('button',{name:'Publish correction',exact:true}).click();
  await page.getByText('Correction published to the customer.',{exact:true}).waitFor();
  await page.screenshot({path:resolve(output,'live-admin-resolution.png'),fullPage:true});
  report.checks.admin_correction_published=true;
  await page.getByRole('link',{name:'Customer portal',exact:true}).click();
  await page.getByRole('button',{name:'#'+String(result.ticket.id).padStart(4,'0'),exact:false}).click();
  await page.getByText('Updated answer',{exact:true}).waitFor();
  await page.getByText('Your fictional browser-verification enquiry has been reviewed by the support team. No account action was needed.',{exact:true}).waitFor();
  await page.screenshot({path:resolve(output,'live-customer-resolution.png'),fullPage:true});
  report.checks.customer_sees_admin_correction=true;
  await page.getByLabel('Still need help?',{exact:true}).fill('Please review this fictional enquiry once more.');
  await page.getByRole('button',{name:'Send to support team',exact:true}).click();
  await page.getByText('Our support team is reviewing your enquiry.',{exact:true}).waitFor();
  report.checks.customer_can_reopen=true;
  assert.deepEqual(errors,[]);
  report.checks.no_browser_errors=true;
} finally {
  if(signedIn){
    await page.goto(base);
    await page.getByRole('button',{name:'End demo & delete data',exact:true}).click();
    await page.getByRole('button',{name:'Try the demo',exact:true}).waitFor();
    assert.equal((await context.request.get(base+'/api/portal/tickets')).status(),401);
    report.checks.demo_deleted_and_customer_session_revoked=true;
  }
  await context.close();
  await browser.close();
}
report.passed=true;
await writeFile(resolve(output,'live-browser-resolution.json'),JSON.stringify(report,null,2)+'\n');
process.stdout.write(JSON.stringify(report,null,2)+'\n');
