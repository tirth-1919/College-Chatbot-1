import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = { scenarios: { chats: { executor: 'constant-vus', vus: 500, duration: '5m' } } };
const base = __ENV.BASE_URL || 'http://localhost:8000/api/v1';
const origin = __ENV.ORIGIN || 'http://localhost:3000';
export function setup() {
  const r=http.post(`${base}/auth/login`,JSON.stringify({email:__ENV.TEST_EMAIL,password:__ENV.TEST_PASSWORD}),{headers:{'Content-Type':'application/json','Origin':origin}});
  if(r.status!==200) throw new Error('Load-test login failed');
  return {cookie:r.cookies.access_token?.[0]?.value};
}
export default function(data) {
  const r=http.post(`${base}/chat`,JSON.stringify({message:'college information',conversation_id:null}),{headers:{'Content-Type':'application/json','Origin':origin,Cookie:`access_token=${data.cookie}`}});
  check(r,{'chat response is within service':x=>x.status===200||x.status===429});
  sleep(.2);
}
