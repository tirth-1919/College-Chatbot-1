const base=(process.env.BASE_URL||"http://localhost:8000/api/v1").replace(/\/$/,"");
const origin=process.env.ORIGIN||"http://localhost:3000";
const email=process.env.TEST_EMAIL;
const password=process.env.TEST_PASSWORD;
const url=process.env.CRAWL_URL;
if(!email||!password||!url) throw new Error("Set TEST_EMAIL, TEST_PASSWORD, and a registered HTTPS CRAWL_URL");

async function request(path,options={}){
  const response=await fetch(`${base}${path}`,{...options,headers:{Origin:origin,...options.headers}});
  const body=await response.json().catch(()=>({}));
  if(!response.ok) throw new Error(`${path}: ${response.status} ${body.detail||"request failed"}`);
  return {response,body};
}

const login=await fetch(`${base}/auth/login`,{method:"POST",headers:{"Content-Type":"application/json",Origin:origin},body:JSON.stringify({email,password})});
if(!login.ok) throw new Error(`Login failed: ${login.status}`);
const cookies=(login.headers.getSetCookie?.()||[]).map(value=>value.split(";")[0]).join("; ");
if(!cookies.includes("access_token=")) throw new Error("Login response did not issue an access cookie");
const started=await request("/admin/crawl",{method:"POST",headers:{"Content-Type":"application/json",Cookie:cookies},body:JSON.stringify({url})});
const jobId=started.body.id;
const deadline=Date.now()+40*60*1000;
while(Date.now()<deadline){
  await new Promise(resolve=>setTimeout(resolve,5000));
  const result=await request("/admin/crawls",{headers:{Cookie:cookies}});
  const job=result.body.find(item=>item.id===jobId);
  if(!job) throw new Error(`Crawl job ${jobId} disappeared`);
  console.log(JSON.stringify({id:job.id,status:job.status,found:job.pages_found,done:job.pages_done,failed:job.pages_failed}));
  if(["completed","failed"].includes(job.status)){
    if(job.status!=="completed"||job.pages_done===0) process.exitCode=1;
    break;
  }
}
if(Date.now()>=deadline){console.error("Crawl exceeded the 40-minute smoke-test window");process.exitCode=1;}
