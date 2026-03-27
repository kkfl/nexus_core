const puppeteer = require('puppeteer');

(async () => {
    const browser = await puppeteer.launch({ headless: "new", args: ['--no-sandbox'] });
    const page = await browser.newPage();
    page.on('console', msg => console.log('BROWSER_CONSOLE:', msg.text()));
    page.on('request', request => {
        if (request.url().includes('email')) {
            console.log(`[REQ] ${request.method()} ${request.url()}`);
        }
    });
    page.on('response', async response => {
        if (response.url().includes('email')) {
            console.log(`[RES] ${response.status()} ${response.url()}`);
            if (response.headers()['content-type']?.includes('text/html') && response.url().includes('dns')) {
                console.log('WARNING! API request received text/html:', response.url());
                const body = await response.text();
                // console.log('HTML SNIPPET:', body.substring(0, 200));
            }
        }
    });
    
    await page.evaluateOnNewDocument(() => {
        window.addEventListener('error', e => {
            console.log('WINDOW_ERROR:', e.message);
            if (e.error && e.error.stack) console.log('STACK:', e.error.stack);
        });
        window.addEventListener('unhandledrejection', e => {
            console.log('UNHANDLED_REJECTION:', e.reason);
        });
    });

    console.log("Navigating to http://127.0.0.1:3000/login");
    try {
        await page.goto('http://127.0.0.1:3000/login', { waitUntil: 'domcontentloaded' });
        
        console.log("Typing credentials...");
        await page.type('#login_username', 'rpowell@gsmcall.com');
        await page.type('#login_password', 'password');
        console.log("Submitting...");
        await page.click('button[type="submit"]');
        
        console.log("Waiting 2s for login process...");
        await new Promise(r => setTimeout(r, 2000));
        
        console.log("Navigating to dns integrations...");
        await page.goto('http://127.0.0.1:3000/integrations/dns', { waitUntil: 'domcontentloaded' });
        
        console.log("Waiting 10s for render crashes...");
        await new Promise(r => setTimeout(r, 10000));
        
        const html = await page.evaluate(() => document.getElementById('root')?.innerHTML || 'NO_ROOT');
        if (html.length < 500) {
            console.log('ROOT IS SUSPICIOUSLY SHORT:', html);
        } else {
            console.log('ROOT IS OK, length:', html.length);
        }
        
        console.log("Taking screenshot...");
        await page.screenshot({ path: 'c:/Users/randa/.gemini/antigravity/brain/a7f17d10-a89d-4d1b-a9ac-5930b7a8f743/debug_email_page.png' });
        console.log("Done.");

    } catch (e) {
        console.log("Script error:", e);
    }
    
    await browser.close();
})();
