"use client";

import React, { createContext, FormEvent, KeyboardEvent, useContext, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import en from "../messages/en.json";
import hi from "../messages/hi.json";
import gu from "../messages/gu.json";
const getApiBase = () => {
  return process.env.NEXT_PUBLIC_ADMIN_API_URL || "http://localhost:8001/api/v1";
};
const ENV_ADMIN_MODE = true;
const MessagesContext=createContext(en);
const useMessages=()=>useContext(MessagesContext);
function errorText(value:unknown,fallback:string):string{
  if(typeof value==="string"&&value.trim())return value;
  if(value instanceof Error&&value.message.trim())return value.message;
  if(value&&typeof value==="object"){
    const detail=(value as {detail?:unknown}).detail;
    if(typeof detail==="string"&&detail.trim())return detail;
    if(Array.isArray(detail)){
      const messages=detail.map(item=>typeof item==="string"?item:item&&typeof item==="object"&&typeof (item as {msg?:unknown}).msg==="string"?(item as {msg:string}).msg:"").filter(Boolean);
      if(messages.length)return messages.join("; ");
    }
  }
  return fallback;
}
type User = { id:number; name:string; email:string; role:string; college_id:number|null; force_password_change?:boolean; mfa_enabled?:boolean };
type Chat = { id:number; title:string; college_id:number|null; college_name?:string; updated_at?:string; pinned?:boolean };
type Source = { url:string; updated_at?:string; type?:string; thumbnail_url?:string; alt_text?:string; source_url?:string };
type Message = { id?:number; role:string; content:string; source_badge?:string; sources?:Source[]; contact?:{phone?:string|null;email?:string|null}; location?:{address:string;latitude:number|null;longitude:number|null} };

let refreshInFlight: Promise<boolean> | null = null;
function refreshSession(baseUrl:string): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(baseUrl+"/auth/refresh", {method:"POST", credentials:"include"})
      .then(response=>response.ok)
      .catch(()=>false)
      .finally(()=>{refreshInFlight=null;});
  }
  return refreshInFlight;
}

function groupChatsByIstDate(chats:Chat[],labels:any){
  const dayKey=(date:Date)=>new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Kolkata",year:"numeric",month:"2-digit",day:"2-digit"}).format(date);
  const today=dayKey(new Date());
  const dayNumber=(key:string)=>Date.parse(`${key}T00:00:00Z`);
  const groups=new Map<string,Chat[]>();
  for(const chat of chats){
    const key=chat.updated_at?dayKey(new Date(chat.updated_at)):"";
    const days=key?Math.floor((dayNumber(today)-dayNumber(key))/86400000):Infinity;
    const label=days<=0?labels.historyToday:days===1?labels.historyYesterday:days<7?labels.historyPrevious7:days<30?labels.historyPrevious30:labels.historyOlder;
    groups.set(label,[...(groups.get(label)||[]),chat]);
  }
  return [...groups.entries()];
}

async function api(path:string, init:RequestInit={}, retry=true):Promise<any> {
  const form = typeof FormData !== "undefined" && init.body instanceof FormData;
  const headers = { ...(form ? {} : {"Content-Type":"application/json"}), ...(init.headers || {}) };
  const baseUrl = getApiBase();
  let response:Response;
  try {
    response = await fetch(baseUrl + path, {...init, credentials:"include", headers});
  } catch (error:any) {
    const cause=error instanceof Error?error.message:String(error);
    throw new Error(`Request to ${baseUrl+path} failed: ${cause}. Check the browser console for CORS or connection details.`);
  }
  if (response.status===401 && retry && !/^\/auth\/(login|signup|refresh|logout|verify-email|verify-mfa|forgot-password|reset-password)/.test(path)) {
    if (await refreshSession(baseUrl)) {
      response = await fetch(baseUrl+path, {...init, credentials:"include", headers});
    }
  }
  const raw = await response.text();
  let data:any = {};
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = {detail:raw}; }
  if (!response.ok) throw new Error(errorText(data.detail,`${response.status}: ${response.statusText}`));
  return data;
}

export default function Home() {
  const [adminMode,setAdminMode]=useState(ENV_ADMIN_MODE);
  const [user,setUser]=useState<User|null>(null), [auth,setAuth]=useState(ENV_ADMIN_MODE), [login,setLogin]=useState(true);
  const [verify,setVerify]=useState(false), [mfaChallenge,setMfaChallenge]=useState(false), [pendingEmail,setPendingEmail]=useState(""), [devCode,setDevCode]=useState("");
  const [chats,setChats]=useState<Chat[]>([]), [cid,setCid]=useState<number|null>(null), [messages,setMessages]=useState<Message[]>([]);
  const [text,setText]=useState(""), [college,setCollege]=useState(""), [collegeId,setCollegeId]=useState<number|null>(null);
  const [collegePickerOpen,setCollegePickerOpen]=useState(false),[collegeDraft,setCollegeDraft]=useState(""),[copyFallback,setCopyFallback]=useState("");
  const [resetOpen,setResetOpen]=useState(false),[resetStep,setResetStep]=useState<"request"|"reset">("request"),[resetEmail,setResetEmail]=useState(""),[resetCode,setResetCode]=useState(""),[resetPassword,setResetPassword]=useState(""),[resetMessage,setResetMessage]=useState("");
  const [suggestions,setSuggestions]=useState<string[]>([]), [attachment,setAttachment]=useState<File|null>(null); const [collegeOptions,setCollegeOptions]=useState<Array<{id:number;name:string;code:string}>>([]);
  const [error,setError]=useState(""), [busy,setBusy]=useState(false), [language,setLanguage]=useState("en-IN"), [settingsOpen,setSettingsOpen]=useState(false), [accountMenuOpen,setAccountMenuOpen]=useState(false);
  const [adminData,setAdminData]=useState<any>(null),[featureFlags,setFeatureFlags]=useState<any>({voice:true,widget:true,semantic_search:true}),[unread,setUnread]=useState(0),[isOnline,setIsOnline]=useState(true),[recording,setRecording]=useState(false),[codingMode,setCodingMode]=useState(false); const recorder=useRef<MediaRecorder|null>(null),speechRecognizer=useRef<any>(null); const bottom=useRef<HTMLDivElement>(null),messagesBox=useRef<HTMLDivElement>(null),atBottom=useRef(true),previousMessageCount=useRef(0); const aborter=useRef<AbortController|null>(null);
  const labels=language==="hi-IN"?hi:language==="gu-IN"?gu:en;

  useEffect(()=>{setAdminMode(ENV_ADMIN_MODE);if(ENV_ADMIN_MODE)setAuth(true);},[]);
  useEffect(()=>{api("/auth/me").then(async u=>{
    setUser(u);
    if(adminMode && !["super_admin","college_admin","editor","viewer"].includes(u.role)){
      setError("Admin access required. Please sign in with an admin account.");
      setAuth(true);
      return;
    }
    if(u.role==="super_admin") setAdminData(await api("/super/overview"));
    else if(["college_admin","editor","viewer"].includes(u.role)) setAdminData(await api("/admin/overview"));
    else setChats(await api("/conversations"));
  }).catch(()=>setAuth(true));},[adminMode]);
  useEffect(()=>{const update=()=>setIsOnline(navigator.onLine);update();window.addEventListener("online",update);window.addEventListener("offline",update);return()=>{window.removeEventListener("online",update);window.removeEventListener("offline",update);};},[]);
  useEffect(()=>{const added=Math.max(0,messages.length-previousMessageCount.current);previousMessageCount.current=messages.length;if(!added)return;if(atBottom.current){bottom.current?.scrollIntoView({behavior:"smooth"});setUnread(0);}else setUnread(count=>count+added);},[messages]);
  useEffect(()=>{if(busy&&atBottom.current)bottom.current?.scrollIntoView({behavior:"smooth"});},[busy]);
  function scrollToLatest(){atBottom.current=true;setUnread(0);bottom.current?.scrollIntoView({behavior:"smooth"});}
  function resetChatScroll(){atBottom.current=true;previousMessageCount.current=0;setUnread(0);}

  async function authenticate(e:FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); const form=e.currentTarget; const data=new FormData(form);
    try {
      if(login) {
        const u=await api("/auth/login",{method:"POST",body:JSON.stringify({email:data.get("email"),password:data.get("password")})});
        if(u.mfa_required){setPendingEmail(u.email);setDevCode(u.development_code||"");setMfaChallenge(true);setError("A sign-in code was sent to your email.");return;}
        setUser(u);setAuth(false);
        if(u.role==="super_admin")setAdminData(await api("/super/overview"));
        else if(["college_admin","editor","viewer"].includes(u.role))setAdminData(await api("/admin/overview"));
        else setChats(await api("/conversations"));
      } else {
        const email=String(data.get("email")); const result=await api("/auth/signup",{method:"POST",body:JSON.stringify({name:data.get("name"),email,password:data.get("password"),consent:data.get("consent")==="on"})});
        setPendingEmail(email);setDevCode(result.development_code||"");setVerify(true);setError(result.message);
      }
    } catch(e:any) {setError(e.message);}
  }
  async function verifyMfa(e:FormEvent<HTMLFormElement>){e.preventDefault();try{const code=new FormData(e.currentTarget).get("code");const u=await api("/auth/verify-mfa",{method:"POST",body:JSON.stringify({email:pendingEmail,code})});setMfaChallenge(false);setUser(u);setAuth(false);if(u.role==="super_admin")setAdminData(await api("/super/overview"));else if(["college_admin","editor","viewer"].includes(u.role))setAdminData(await api("/admin/overview"));else setChats(await api("/conversations"));}catch(e:any){setError(e.message);}}
  async function verifyEmail(e:FormEvent<HTMLFormElement>){e.preventDefault();try{const code=new FormData(e.currentTarget).get("code");await api("/auth/verify-email",{method:"POST",body:JSON.stringify({email:pendingEmail,code})});setVerify(false);setLogin(true);setError("Email verified. Sign in to continue.");}catch(e:any){setError(e.message);}}
  async function forgotPassword(){setResetOpen(true);setResetStep("request");setResetMessage("");}
  async function requestPasswordReset(e:FormEvent<HTMLFormElement>){e.preventDefault();try{const result=await api("/auth/forgot-password",{method:"POST",body:JSON.stringify({email:resetEmail})});setResetCode(result.development_code||"");setResetMessage(result.message||"If the account exists, a reset code has been sent.");setResetStep("reset");}catch(e:any){setResetMessage(e.message);}}
  async function completePasswordReset(e:FormEvent<HTMLFormElement>){e.preventDefault();try{await api("/auth/reset-password",{method:"POST",body:JSON.stringify({email:resetEmail,code:resetCode,password:resetPassword})});setResetOpen(false);setResetPassword("");setError("If the account exists, the password reset is complete.");}catch(e:any){setResetMessage(e.message);}}
  async function copyText(value:string){try{if(!navigator.clipboard?.writeText)throw new Error("Clipboard unavailable");await navigator.clipboard.writeText(value);}catch{setCopyFallback(value);}}
  function applyCollege(){const name=collegeDraft.trim();if(!name)return;setText(name);setCollegePickerOpen(false);}
  async function logout(){await api("/auth/logout",{method:"POST"});setUser(null);setAuth(true);setMessages([]);}
  async function newChat(){const c=await api("/conversations",{method:"POST"});resetChatScroll();setCid(c.id);setMessages([]);setCollegeOptions([]);setCollegeId(null);setFeatureFlags({voice:true,widget:true,semantic_search:true});setSuggestions([]);setCollege("");}
  async function openChat(c:Chat){resetChatScroll();setCollegeOptions([]);setCid(c.id);setCollege(c.college_name||"");setCollegeId(c.college_id);if(c.college_id){setFeatureFlags(await api(`/colleges/${c.college_id}/features`).catch(()=>({voice:true,widget:true,semantic_search:true})));setSuggestions(await api(`/colleges/${c.college_id}/suggestions`));}else{setFeatureFlags({voice:true,widget:true,semantic_search:true});setSuggestions([]);}const msgs=await api(`/conversations/${c.id}/messages`);setMessages(msgs);}
  async function send(value=text){const question=value.trim();if((!question&&!attachment)||busy)return;setError("");setText("");setBusy(true);setMessages(m=>[...m,{role:"user",content:question||`Attached ${attachment?.name}`}]);aborter.current=new AbortController();
    try {let result:any;
      if(attachment){const fd=new FormData();fd.set("file",attachment);fd.set("question",question);fd.set("language",language);if(cid)fd.set("conversation_id",String(cid));result=await api("/chat/attachment",{method:"POST",body:fd,signal:aborter.current.signal});setAttachment(null);}
      else{result=await api("/chat",{method:"POST",body:JSON.stringify({conversation_id:cid,message:question,language}),signal:aborter.current.signal});}
      setCid(result.conversation_id);setCollegeOptions(result.college_options||[]);setCollege(result.college_name||college);setCollegeId(result.college_id||null);if(result.college_id){setFeatureFlags(await api(`/colleges/${result.college_id}/features`).catch(()=>({voice:true,widget:true,semantic_search:true})));setSuggestions(await api(`/colleges/${result.college_id}/suggestions`));}setMessages(m=>{const next=[...m];const index=next.map(item=>item.role).lastIndexOf("user");if(typeof result.user_message_id==="number"&&index>=0&&!next[index].id)next[index]={...next[index],id:result.user_message_id};next.push({...result.message,contact:result.college_contact,location:result.college_location});return next;});setChats(await api("/conversations"));
    } catch(e:any){if(e.name!=="AbortError")setError(e.message);}finally{setBusy(false);aborter.current=null;}
  }
  async function voiceInput(){
    if(featureFlags.voice===false){setError(labels.voiceDisabled);return;}
    if(recording||speechRecognizer.current||recorder.current){
      if(speechRecognizer.current){try{speechRecognizer.current.stop();}catch{};return;}
      if(recorder.current?.state==="recording"){recorder.current.stop();return;}
    }
    const Speech=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;
    if(Speech){
      const rec=new Speech();let recognized=false;
      rec.lang=language;rec.interimResults=true;rec.continuous=false;speechRecognizer.current=rec;setError("");
      rec.onstart=()=>setRecording(true);
      rec.onresult=(event:any)=>{recognized=true;const transcript=Array.from(event.results as ArrayLike<any>).map((result:any)=>result[0]?.transcript||"").join(" ").trim();if(transcript)setText([text.trim(),transcript].filter(Boolean).join(" "));};
      rec.onnomatch=()=>setError(labels.voiceNoSpeech);
      rec.onerror=(event:any)=>{const messages:Record<string,string>={"no-speech":labels.voiceNoSpeech,"not-allowed":labels.voicePermissionDenied,"service-not-allowed":labels.voicePermissionDenied,"audio-capture":labels.voiceUnavailable,network:labels.voiceNetworkError,"language-not-supported":labels.voiceLanguageUnsupported};if(event.error!=="aborted")setError(messages[event.error]||labels.voiceRecognitionError);setRecording(false);};
      rec.onend=()=>{speechRecognizer.current=null;setRecording(false);if(!recognized)setError(current=>current||labels.voiceNoSpeech);};
      try{rec.start();}catch(e:any){speechRecognizer.current=null;setRecording(false);setError(e.name==="NotAllowedError"?labels.voicePermissionDenied:labels.voiceRecognitionError);}
      return;
    }
    if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==="undefined"){setError(labels.voiceUnavailable);return;}
    try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});const mime=["audio/webm;codecs=opus","audio/webm","audio/mp4","audio/ogg"].find(type=>MediaRecorder.isTypeSupported(type));const media=new MediaRecorder(stream,mime?{mimeType:mime}:undefined);const chunks:BlobPart[]=[];media.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};media.onstop=async()=>{stream.getTracks().forEach(track=>track.stop());setRecording(false);recorder.current=null;if(!chunks.length){setError(labels.voiceNoSpeech);return;}try{const audioMime=media.mimeType||mime||"audio/webm";const form=new FormData();form.set("file",new Blob(chunks,{type:audioMime}),audioMime.includes("mp4")?"voice.mp4":audioMime.includes("ogg")?"voice.ogg":"voice.webm");if(cid)form.set("conversation_id",String(cid));form.set("language",language);const result=await api("/audio/transcribe",{method:"POST",body:form});setText((current:string)=>[current,result.text].filter(Boolean).join(" "));setError("");}catch(e:any){setError(e.message);}};recorder.current=media;media.start();setRecording(true);setError("");}catch(e:any){setError(e.name==="NotAllowedError"?labels.voicePermissionDenied:e.message||labels.voiceUnavailable);}
  }
  async function feedback(message:Message,rating:string,reason=""){if(message.id)await api("/feedback",{method:"POST",body:JSON.stringify({message_id:message.id,rating,reason})});}

  if(adminMode && user && !["super_admin","college_admin","editor","viewer"].includes(user.role))return <AdminLoginPanel onLogin={async(u)=>{setUser(u);setAuth(false);if(u.role==="super_admin")setAdminData(await api("/super/overview"));else setAdminData(await api("/admin/overview"));}}/>;
  if(!user&&auth&&adminMode)return <AdminLoginPanel onLogin={async(u)=>{setUser(u);setAuth(false);if(u.role==="super_admin")setAdminData(await api("/super/overview"));else setAdminData(await api("/admin/overview"));}}/>;
  if(!user&&auth)return <MessagesContext.Provider value={labels}><div className="modal"><div className="card"><div className="card-header"><img src="/ai-faq-logo.png" alt="AI FAQ College Chat Bot" className="card-logo"/><h2 style={{margin:"0 0 2px",fontSize:"18px",fontWeight:700,color:"#fff"}}>AI FAQ College Chat Bot</h2><p className="subtitle">User Portal</p></div><LanguagePicker language={language} onChange={setLanguage}/>
    {mfaChallenge?<form onSubmit={verifyMfa}><h2>{labels.twoStep}</h2><p className="muted">{labels.enterCodeSent} {pendingEmail}.</p><input name="code" inputMode="numeric" autoComplete="one-time-code" placeholder="6-digit code" required/>{devCode&&<p className="muted">{labels.developmentCode} <b>{devCode}</b></p>}{error&&<p className="error">{error}</p>}<button className="primary">{labels.continue}</button></form>:verify?<form onSubmit={verifyEmail}><h2>{labels.verifyEmail}</h2><p className="muted">{labels.enterCodeSent} {pendingEmail}.</p><input name="code" placeholder="6-digit code" required/>{devCode&&<p className="muted">{labels.developmentCode} <b>{devCode}</b></p>}{error&&<p className="error">{error}</p>}<button className="primary">{labels.verify}</button></form>:
    <><form onSubmit={authenticate}><h2>{login?labels.welcomeBack:labels.createAccount}</h2><p className="muted">{labels.chatIntro}</p>{!login&&<input name="name" placeholder={labels.fullName} required/>}<input name="email" type="email" placeholder={labels.email} required/><input name="password" type="password" placeholder="Password (8+ characters)" minLength={login?undefined:8} required/>{!login&&<label className="muted"><input type="checkbox" name="consent" required/> {labels.consent} <a href="/privacy" target="_blank" rel="noreferrer">{labels.privacyNotice}</a> {labels.terms}.</label>}{error&&<p className="error">{error}</p>}<button className="primary" style={{width:"100%"}}>{login?labels.signIn:labels.createAccount}</button>{login&&<p className="muted link" onClick={forgotPassword}>{labels.forgotPassword}</p>}<p className="muted link" onClick={()=>{setLogin(!login);setError("")}}>{login?labels.createAccount:labels.alreadyRegistered}</p></form><details><summary className="btn">{labels.registerCollege}</summary><RegisterForm/></details></>}
  </div></div>{resetOpen&&<div className="modal"><div className="card" role="dialog" aria-modal="true" aria-labelledby="reset-title"><button type="button" className="mini" onClick={()=>setResetOpen(false)}>{labels.close}</button><h2 id="reset-title">Reset password</h2>{resetStep==="request"?<form onSubmit={requestPasswordReset}><input type="email" autoComplete="email" placeholder={labels.email} value={resetEmail} onChange={e=>setResetEmail(e.target.value)} required/><button className="primary">Send reset code</button></form>:<form onSubmit={completePasswordReset}><p className="muted">{resetMessage}</p><input inputMode="numeric" autoComplete="one-time-code" placeholder="Reset code" value={resetCode} onChange={e=>setResetCode(e.target.value)} required/><input type="password" autoComplete="new-password" placeholder="New password" value={resetPassword} onChange={e=>setResetPassword(e.target.value)} minLength={8} required/><button className="primary">Reset password</button></form>}{resetMessage&&resetStep==="request"&&<p className="muted">{resetMessage}</p>}</div></div>}</MessagesContext.Provider>;
  if(!user)return <div className="modal"><button className="primary" onClick={()=>setAuth(true)}>Sign in</button></div>;
  if(user.force_password_change)return <MessagesContext.Provider value={labels}><ChangePassword onDone={async()=>{await logout();setError("Password changed. Sign in again.");}}/></MessagesContext.Provider>;
  if(adminMode && user.role==="super_admin")return <MessagesContext.Provider value={labels}><SuperAdmin user={user} data={adminData} refresh={async()=>setAdminData(await api("/super/overview"))} onLogout={logout} language={language} setLanguage={setLanguage}/></MessagesContext.Provider>;
  if(adminMode && user.role!=="user")return <MessagesContext.Provider value={labels}><CollegeAdmin user={user} data={adminData} refresh={async()=>setAdminData(await api("/admin/overview"))} onLogout={logout} language={language} setLanguage={setLanguage}/></MessagesContext.Provider>;

  return <MessagesContext.Provider value={labels}><div className="shell"><aside className="sidebar"><div className="brand"><img src="/ai-faq-logo.png" alt="AI FAQ College Chat Bot" className="brand-logo"/><span className="brand-text"><span className="brand-name">AI FAQ</span><span className="brand-sub">College Chat Bot</span></span></div><button className="btn" onClick={newChat}>{labels.newChat}</button><input aria-label="Search chat history" placeholder="Search chats" onChange={async e=>{const all=await api("/conversations");setChats(all.filter((c:Chat)=>c.title.toLowerCase().includes(e.target.value.toLowerCase())));}}/><ChatHistory chats={chats} selectedId={cid} onOpen={openChat} onRefresh={async()=>setChats(await api("/conversations"))} onDeleted={id=>{if(cid===id){setCid(null);setMessages([]);setCollegeId(null);setCollege("");}}}/><div className="account-menu-anchor">{accountMenuOpen&&<div className="account-menu" role="menu"><div className="account-menu-identity"><div className="user-name">{user.name}</div><div className="user-email">{user.email}</div></div><button role="menuitem" onClick={()=>{setAccountMenuOpen(false);setSettingsOpen(true);}}><span className="account-menu-icon">◉</span>Profile and security</button><button role="menuitem" onClick={()=>{setAccountMenuOpen(false);setSettingsOpen(true);}}><span className="account-menu-icon">⚙</span>{labels.settings}</button><div className="account-menu-divider"/><button role="menuitem" onClick={async()=>{setAccountMenuOpen(false);await logout();}}><span className="account-menu-icon">↪</span>{labels.signOut}</button></div>}<div className="user-profile"><div className="user-avatar">{user.name.charAt(0).toUpperCase()}</div><div className="user-info"><div className="user-name">{user.name}</div><div className="user-email">{user.email}</div></div><button className="profile-menu-btn" aria-label="Open account menu" aria-haspopup="menu" aria-expanded={accountMenuOpen} onClick={()=>setAccountMenuOpen(v=>!v)}>&#8942;</button></div></div></aside>
    <main className="main"><MaintenanceBanner/><header className="top"><button className="college-chip" onClick={()=>{setCollegeDraft(college);setCollegePickerOpen(true);}}>{college||labels.chooseCollege}&#12296;</button><LanguagePicker language={language} onChange={setLanguage}/></header>
      <div className="messages" ref={messagesBox} onScroll={e=>{const node=e.currentTarget;const nearBottom=node.scrollHeight-node.scrollTop-node.clientHeight<80;atBottom.current=nearBottom;if(nearBottom)setUnread(0);}}><div className="thread">{!messages.length&&<div className="welcome"><img src="/ai-faq-logo.png" alt="AI FAQ College Chat Bot" className="welcome-logo"/><h1>{labels.chatTitle}</h1><p className="tagline">{labels.welcome}</p></div>}
        {collegeId&&suggestions.length>0&&<div className="suggestions">{suggestions.map(s=><button className="btn" key={s} onClick={()=>setText(s)}>{s}</button>)}</div>}{collegeOptions.length>0&&<div className="suggestions" role="group" aria-label={labels.chooseCollege}>{collegeOptions.map(option=><button className="btn" key={option.id} onClick={()=>{setCollegeOptions([]);send(option.name);}}>{option.name} · {option.code}</button>)}</div>}
        {messages.map((m,i)=><div className={`row ${m.role}`} key={m.id||i}><div className="bubble"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>{m.location&&<div className="panel"><b>{labels.locationMap}</b>{m.location.latitude!==null&&m.location.longitude!==null&&<iframe title={labels.locationMap} loading="lazy" referrerPolicy="no-referrer-when-downgrade" src={`https://www.google.com/maps?q=${m.location.latitude},${m.location.longitude}&output=embed`} style={{width:"100%",height:"220px",border:0,borderRadius:"10px"}}/>}<p>{m.location.address}</p><a target="_blank" rel="noreferrer" href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(m.location.latitude!==null&&m.location.longitude!==null?`${m.location.latitude},${m.location.longitude}`:m.location.address)}`}>{labels.directions}</a></div>}{m.source_badge&&<div className="badge">&#9679; {m.source_badge}</div>}{m.sources?.map((s,j)=>s.type==="image"?<a className="source" target="_blank" rel="noreferrer" href={s.url} key={`${m.id||i}-${j}`}><img src={s.thumbnail_url||s.url} alt={s.alt_text||labels.collegeImage} loading="lazy" style={{maxWidth:"240px",maxHeight:"180px",objectFit:"cover",borderRadius:"10px",display:"block"}}/>{s.alt_text||s.source_url}</a>:<a className="source" target="_blank" rel="noreferrer" href={s.url} key={`${m.id||i}-${j}`}>{s.url}{s.updated_at?` · ${labels.updated} ${new Date(s.updated_at).toLocaleDateString("en-IN",{timeZone:"Asia/Kolkata"})}`:""}</a>)}<div className="actions">{m.role==="assistant"?<><button onClick={()=>copyText(m.content)}>{labels.copy}</button><button onClick={()=>feedback(m,"up")}>&#128077;</button><button onClick={()=>feedback(m,"down")}>&#128078;</button><button onClick={()=>feedback(m,"down","Reported by user")}>{labels.report}</button><button onClick={()=>window.speechSynthesis.speak(new SpeechSynthesisUtterance(m.content))}>{labels.readAloud}</button><button onClick={async()=>{const last=[...messages].slice(0,i).reverse().find(x=>x.role==="user");if(last&&cid&&typeof last.id==="number"){const lastId=last.id;await api(`/conversations/${cid}/truncate`,{method:"POST",body:JSON.stringify({message_id:lastId})});setMessages(messages.filter(x=>typeof x.id==="number"&&x.id<lastId));send(last.content);}}}>{labels.regenerate}</button></>:<button onClick={async()=>{if(cid&&m.id){await api(`/conversations/${cid}/truncate`,{method:"POST",body:JSON.stringify({message_id:m.id})});setMessages(messages.slice(0,i));}setText(m.content);}}>{labels.editResend}</button>}</div>{m.role==="assistant"&&collegeId&&(m.content.startsWith("Not available")||m.content.toLowerCase().includes("submit an enquiry"))&&<><p className="muted">{m.contact?.phone&&<>☎ <a href={`tel:${m.contact.phone}`}>{m.contact.phone}</a> </>}{m.contact?.email&&<>✉ <a href={`mailto:${m.contact.email}`}>{m.contact.email}</a></>}</p><EnquiryForm collegeId={collegeId} user={user} initialMessage={[...messages].slice(0,i).reverse().find(x=>x.role==="user")?.content||""}/></>}</div></div>)}
        {busy&&<div className="row"><div className="bubble muted" role="status" aria-live="polite">{labels.working}</div></div>}<div ref={bottom}/></div>{unread>0&&<button className="scroll-bottom" onClick={scrollToLatest}>{labels.scrollToBottom}{unread>1?` · ${unread}`:""}</button>}</div>
      {!isOnline&&<p className="error" role="status">{labels.offline}</p>}{error&&<p className="error" role="alert" style={{textAlign:"center"}}>{error}</p>}
      <div className="composer">{busy&&<button className="btn" onClick={()=>aborter.current?.abort()}>{labels.stop}</button>}{attachment&&<p className="muted">Attached {attachment.name} <button className="mini" onClick={()=>setAttachment(null)}>Remove</button></p>}{codingMode&&<span className="coding-badge">Coding Mode</span>}
        <div className="inputbox"><label className="btn" aria-label="Attach a document or image">&#65291;<input hidden type="file" accept=".pdf,.docx,.png,.jpg,.jpeg,.webp" onChange={e=>setAttachment(e.target.files?.[0]||null)}/></label><textarea aria-label="Ask a college question" rows={1} value={text} placeholder={codingMode?"Ask a coding question...":labels.askAnything} onChange={e=>setText(e.target.value)} onKeyDown={(e:KeyboardEvent<HTMLTextAreaElement>)=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}}}/><button type="button" className={`btn icon-button ${codingMode?"active":""}`} aria-label="Coding mode" aria-pressed={codingMode} onClick={()=>setCodingMode(!codingMode)} title="Toggle Coding mode"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/></svg></button><button type="button" className={`voice-button ${recording?"recording":""}`} aria-label={recording?labels.stopRecording:labels.voiceInput} title={recording?labels.stopRecording:labels.voiceInput} onClick={voiceInput}><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 19v3m-4 0h8"/></svg><span className="sr-only">{recording?labels.stopRecording:labels.voiceInput}</span></button><button className="send" aria-label={labels.send} onClick={()=>send()}>&#8593;</button></div><div className="fineprint">AI FAQ College Chat Bot &middot; Your College, Your Priority</div>
      </div>
    </main>{settingsOpen&&<Settings user={user} close={()=>setSettingsOpen(false)} onLogout={logout}/>}{collegePickerOpen&&<div className="modal"><form className="card" role="dialog" aria-modal="true" onSubmit={e=>{e.preventDefault();applyCollege();}}><button type="button" className="mini" onClick={()=>setCollegePickerOpen(false)}>{labels.close}</button><h2>{labels.chooseCollege}</h2><p className="muted">{labels.collegePrompt}</p><input autoFocus value={collegeDraft} onChange={e=>setCollegeDraft(e.target.value)} aria-label={labels.collegePrompt}/><button className="primary">{labels.chooseCollege}</button></form></div>}{copyFallback&&<div className="modal"><div className="card" role="dialog" aria-modal="true"><button type="button" className="mini" onClick={()=>setCopyFallback("")}>{labels.close}</button><h2>{labels.copy}</h2><p className="muted">Clipboard permission was denied. Select and copy the text below.</p><textarea autoFocus readOnly value={copyFallback} onFocus={e=>e.currentTarget.select()} rows={8}/></div></div>}
  </div></MessagesContext.Provider>;
}


function AdminLoginPanel({onLogin}:{onLogin:(u:any)=>void}){
  const [email,setEmail]=React.useState("");
  const [password,setPassword]=React.useState("");
  const [showPw,setShowPw]=React.useState(false);
  const [remember,setRemember]=React.useState(false);
  const [busy,setBusy]=React.useState(false);
  const [error,setError]=React.useState("");

  async function handleSubmit(e:React.FormEvent<HTMLFormElement>){
    e.preventDefault();
    setError("");setBusy(true);
    try{
      const formData=new FormData();
      formData.set("email",email.trim());
      formData.set("password",password.trim());
      const u=await api("/auth/login",{method:"POST",body:formData});
      if(u.role==="user"){setError("Access denied: this portal is for authorized administrators only.");setBusy(false);return;}
      onLogin(u);
    }catch(e:unknown){setError(errorText(e,"Login failed"));setBusy(false);}
  }

  return(
    <div style={{minHeight:"100vh",background:"#000000",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:"18px",fontFamily:"Inter,system-ui,sans-serif"}}>
      <div style={{background:"#111111",border:"1px solid #2a2a2a",borderRadius:"16px",padding:"40px 36px",width:"min(420px,100%)",boxShadow:"0 8px 40px rgba(0,0,0,0.7)"}}>
        <div style={{textAlign:"center",marginBottom:"32px"}}>
          <img src="/ai-faq-logo.png" alt="AI FAQ College Chat Bot" style={{width:"72px",height:"72px",objectFit:"contain",borderRadius:"14px",marginBottom:"14px"}}/>
          <h1 style={{margin:"0 0 6px",fontSize:"22px",fontWeight:700,color:"#ffffff",letterSpacing:"-0.01em"}}>AI FAQ College Chat Bot</h1>
          <p style={{margin:"0 0 4px",fontSize:"18px",fontWeight:600,color:"#ffffff"}}>Admin Portal</p>
          <p style={{margin:0,fontSize:"13px",color:"#a0a0a0"}}>Sign in to manage college information</p>
        </div>
        <form onSubmit={handleSubmit} style={{display:"flex",flexDirection:"column",gap:"14px"}}>
          <div>
            <label style={{display:"block",fontSize:"12px",fontWeight:600,color:"#a0a0a0",marginBottom:"6px",textTransform:"uppercase" as const,letterSpacing:"0.04em"}}>Email Address</label>
            <input
              type="email"
              value={email}
              onChange={e=>setEmail(e.target.value)}
              placeholder="admin@example.com"
              required
              autoComplete="email"
              style={{background:"#1f1f1f",border:"1px solid #2a2a2a",borderRadius:"9px",padding:"11px 13px",color:"#ffffff",fontSize:"14px",width:"100%",margin:0,outline:"none",boxSizing:"border-box" as const}}
            />
          </div>
          <div>
            <label style={{display:"block",fontSize:"12px",fontWeight:600,color:"#a0a0a0",marginBottom:"6px",textTransform:"uppercase" as const,letterSpacing:"0.04em"}}>Password</label>
            <div style={{position:"relative" as const}}>
              <input
                type={showPw?"text":"password"}
                value={password}
                onChange={e=>setPassword(e.target.value)}
                placeholder="Enter your password"
                required
                autoComplete="current-password"
                style={{background:"#1f1f1f",border:"1px solid #2a2a2a",borderRadius:"9px",padding:"11px 42px 11px 13px",color:"#ffffff",fontSize:"14px",width:"100%",margin:0,outline:"none",boxSizing:"border-box" as const}}
              />
              <button
                type="button"
                onClick={()=>setShowPw(p=>!p)}
                style={{position:"absolute" as const,right:"10px",top:"50%",transform:"translateY(-50%)",background:"none",border:"none",color:"#a0a0a0",cursor:"pointer",fontSize:"15px",padding:"4px",lineHeight:1}}
                aria-label={showPw?"Hide password":"Show password"}
              >{showPw?"[hide]":"[show]"}</button>
            </div>
          </div>
          <label style={{display:"flex",alignItems:"center",gap:"8px",fontSize:"13px",color:"#a0a0a0",cursor:"pointer",userSelect:"none" as const}}>
            <input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)} style={{width:"auto",margin:0,cursor:"pointer"}}/>
            Remember me
          </label>
          {error&&<p style={{margin:0,color:"#fca5a5",fontSize:"13px",padding:"10px 12px",background:"rgba(220,38,38,0.08)",border:"1px solid rgba(220,38,38,0.2)",borderRadius:"8px"}}>{error}</p>}
          <button
            type="submit"
            disabled={busy}
            style={{background:busy?"#2a2a2a":"#eeeeee",color:busy?"#888":"#111111",border:"none",borderRadius:"9px",padding:"12px 16px",fontWeight:700,fontSize:"15px",cursor:busy?"not-allowed":"pointer",marginTop:"4px",transition:"background 0.15s",display:"flex",alignItems:"center",justifyContent:"center",gap:"8px"}}
          >
            {busy&&<span style={{display:"inline-block",width:"14px",height:"14px",border:"2px solid #888",borderTopColor:"transparent",borderRadius:"50%",animation:"admin-spin 0.7s linear infinite"}}/>}
            {busy?"Signing in...":"Sign In"}
          </button>
        </form>
      </div>
      <p style={{marginTop:"24px",fontSize:"12px",color:"#444",textAlign:"center" as const}}>
        AI FAQ College Chat Bot &nbsp;&middot;&nbsp; Authorized administrators only
      </p>
      <style>{`@keyframes admin-spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

function MaintenanceBanner(){
  const labels=useMessages();const [active,setActive]=useState(false);
  useEffect(()=>{let live=true;const check=()=>fetch(getApiBase().replace("/api/v1","")+"/health").then(r=>r.json()).then(data=>{if(live)setActive(!!data.maintenance_mode);}).catch(()=>{});check();const timer=setInterval(check,30000);return()=>{live=false;clearInterval(timer);};},[]);
  return active?<div className="maintenance-banner" role="status">{labels.maintenanceBanner}</div>:null;
}

function LanguagePicker({language,onChange}:{language:string;onChange:(language:string)=>void}){const labels=useMessages();const[open,setOpen]=useState(false);const langMap:Record<string,string>={"en-IN":"🌐 EN","hi-IN":"🌐 HI","gu-IN":"🌐 GU"};return <div className="language-picker-wrapper" style={{position:"relative"}}><button className="language-picker" onClick={()=>setOpen(!open)}>{langMap[language]||"🌐 EN"} &#9662;</button>{open&&<div className="language-dropdown"><button onClick={()=>{onChange("en-IN");setOpen(false);}}>English</button><button onClick={()=>{onChange("hi-IN");setOpen(false);}}>हिन्दी</button><button onClick={()=>{onChange("gu-IN");setOpen(false);}}>ગુજરાતી</button></div>}</div>}

function EnquiryForm({collegeId,user,initialMessage}:{collegeId:number;user:User;initialMessage:string}){const labels=useMessages();const [sent,setSent]=useState(false),[error,setError]=useState("");async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const d=new FormData(e.currentTarget);try{await api("/enquiries",{method:"POST",body:JSON.stringify({college_id:collegeId,name:d.get("name"),email:d.get("email"),phone:d.get("phone"),message:d.get("message")})});setSent(true);}catch(e:any){setError(e.message);}}if(sent)return <p className="muted">{labels.enquirySent}</p>;return <form className="panel" onSubmit={submit}><h3>{labels.contactOffice}</h3><input name="name" defaultValue={user.name} required/><input name="email" type="email" defaultValue={user.email} required/><input name="phone" placeholder={labels.phone}/><textarea name="message" defaultValue={initialMessage} required/><button className="primary">{labels.sendEnquiry}</button>{error&&<p className="error">{error}</p>}</form>}

function RegisterForm(){const labels=useMessages();const [message,setMessage]=useState("");async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const d=Object.fromEntries(new FormData(e.currentTarget));try{const r=await api("/registrations",{method:"POST",body:JSON.stringify(d)});setMessage(r.development_token?`Submitted. Place this verification token at the emailed well-known path: ${r.development_token}`:"Submitted for review. Check the official contact email for the website verification token.");}catch(e:any){setMessage(e.message);}}return <form onSubmit={submit}><input name="name" placeholder="College name" required/><input name="code" placeholder="College code"/><input name="affiliation" placeholder="University / board affiliation"/><input name="website" type="url" placeholder="Official HTTPS website" required/><input name="email" type="email" placeholder="Official college email" required/><input name="contact_name" placeholder="Contact person" required/><input name="contact_email" type="email" placeholder="Contact email" required/><input name="phone" placeholder="Contact phone" required/><input name="designation" placeholder="Designation"/><input name="address" placeholder="Address" required/><input name="city" placeholder="City" required/><input name="state" placeholder="State" required/><input name="country" placeholder="Country" defaultValue="India"/><input name="logo_url" placeholder="Logo URL"/><input name="verification_document" placeholder="Authorization document link"/><input name="description" placeholder="Description"/><input name="highlights" placeholder="Highlights"/><button className="primary">{labels.submitRegistration}</button>{message&&<p className="muted">{message}</p>}</form>}

function ChangePassword({onDone}:{onDone:()=>void}){const labels=useMessages();const [error,setError]=useState("");async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const d=new FormData(e.currentTarget);try{await api("/auth/change-password",{method:"POST",body:JSON.stringify({current_password:d.get("current_password"),new_password:d.get("new_password")})});onDone();}catch(e:any){setError(e.message);}}return <div className="modal"><form className="card" onSubmit={submit}><h2>{labels.changeTempPassword}</h2><input type="password" name="current_password" placeholder={labels.currentPassword} required/><input type="password" name="new_password" placeholder={labels.newPassword} required/>{error&&<p className="error">{error}</p>}<button className="primary">{labels.changePassword}</button></form></div>}

function ChangePasswordInline(){const labels=useMessages();const [error,setError]=useState("");const [current,setCurrent]=useState("");const [newPw,setNewPw]=useState("");async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();try{await api("/auth/change-password",{method:"POST",body:JSON.stringify({current_password:current,new_password:newPw})});setCurrent("");setNewPw("");setError(labels.profileSaved);}catch(e:any){setError(e.message);}}return <form onSubmit={submit} style={{display:"flex",flexDirection:"column",gap:"8px",marginTop:"12px"}}><label style={{fontSize:"12px",fontWeight:600,color:"#a0a0a0"}}>{labels.changePassword}</label><input type="password" placeholder={labels.currentPassword} value={current} onChange={e=>setCurrent(e.target.value)} required style={{background:"#1f1f1f",border:"1px solid #2a2a2a",borderRadius:"9px",padding:"11px 13px",color:"#ffffff",fontSize:"14px",width:"100%",margin:0,outline:"none",boxSizing:"border-box"}}/><input type="password" placeholder={labels.newPassword} value={newPw} onChange={e=>setNewPw(e.target.value)} required style={{background:"#1f1f1f",border:"1px solid #2a2a2a",borderRadius:"9px",padding:"11px 13px",color:"#ffffff",fontSize:"14px",width:"100%",margin:0,outline:"none",boxSizing:"border-box"}}/>{error&&<p style={{margin:0,color:error===labels.profileSaved?"#4ade80":"#fca5a5",fontSize:"13px",padding:"10px 12px",background:error===labels.profileSaved?"rgba(34,197,94,0.08)":"rgba(220,38,38,0.08)",border:error===labels.profileSaved?"1px solid rgba(34,197,94,0.2)":"1px solid rgba(220,38,38,0.2)",borderRadius:"8px"}}>{error}</p>}<button type="submit" className="btn">{labels.changePassword}</button></form>}

function Settings({user,close,onLogout}:{user:User;close:()=>void;onLogout:()=>void}){
  const labels=useMessages();
  const [message,setMessage]=useState(""),[sessions,setSessions]=useState<any[]>([]),[confirming,setConfirming]=useState<""|"mfa"|"erase"|"delete">(""),[password,setPassword]=useState(""),[confirmText,setConfirmText]=useState(""),[enabled,setEnabled]=useState(!!user.mfa_enabled);
  useEffect(()=>{api("/auth/sessions").then(setSessions).catch(()=>{});},[]);
  async function saveProfile(e:FormEvent<HTMLFormElement>){e.preventDefault();try{const d=new FormData(e.currentTarget);const result=await api("/account/profile",{method:"PATCH",body:JSON.stringify({name:d.get("name")})});user.name=result.name;setMessage(labels.profileSaved);}catch(e:any){setMessage(e.message);}}
  async function download(){try{const d=await api("/account/export");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:"application/json"}));a.download="my-college-faq-data.json";a.click();URL.revokeObjectURL(a.href);}catch(e:any){setMessage(e.message);}}
  async function confirmAction(e:FormEvent<HTMLFormElement>){e.preventDefault();try{if(confirming==="erase"){await api("/account/data",{method:"DELETE"});setMessage(labels.deleteHistory+".");}else if(confirming==="delete"){if(confirmText!=="DELETE"){setMessage("Type DELETE to confirm account removal.");return;}await api("/account/delete",{method:"DELETE",body:JSON.stringify({password})});onLogout();return;}else if(confirming==="mfa"){const result=await api("/auth/mfa",{method:"PATCH",body:JSON.stringify({enabled:!enabled,password})});setEnabled(result.enabled);setMessage(result.message);}setConfirming("");setPassword("");setConfirmText("");}catch(e:any){setMessage(e.message);}}
  return <div className="modal"><div className="card"><button className="mini" onClick={close}>{labels.close}</button><h2>{labels.settings}</h2><p>{user.name} · {user.email}</p><form onSubmit={saveProfile}><input name="name" aria-label={labels.profileName} defaultValue={user.name} maxLength={160} required/><button className="btn">{labels.saveProfile}</button></form><ChangePasswordInline/><h3>{labels.profileSecurity}</h3><p className="muted">{labels.emailTwoStep} {enabled?labels.enabled:labels.disabled}</p><button className="btn" onClick={()=>setConfirming("mfa")}>{enabled?labels.disableTwoStep:labels.enableTwoStep}</button><h3>{labels.sessions}</h3>{sessions.map(s=><div key={s.id} className="history-row">{s.device} · {labels.expires} {new Date(s.expires_at).toLocaleString("en-IN",{timeZone:"Asia/Kolkata"})} · {s.active?labels.active:labels.signedOut}{s.active&&<button className="mini" onClick={async()=>{await api(`/auth/sessions/${s.id}`,{method:"DELETE"});setSessions(await api("/auth/sessions"));}}>{labels.signOutDevice}</button>}</div>)}<button className="btn" onClick={download}>{labels.downloadData}</button><button className="btn" onClick={()=>setConfirming("erase")}>{labels.deleteHistory}</button><button className="btn" onClick={()=>setConfirming("delete")}>{labels.deleteAccount}</button>{confirming&&<form className="panel" onSubmit={confirmAction}><h3>{confirming==="mfa"?(enabled?labels.disableTwoStep:labels.enableTwoStep):confirming==="erase"?labels.deleteHistory:labels.deleteAccount}</h3>{confirming==="delete"&&<input value={confirmText} onChange={e=>setConfirmText(e.target.value)} placeholder="Type DELETE to confirm" required/>}{confirming!=="erase"&&<input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder={labels.currentPassword} required/>}<button className="primary">Confirm</button><button type="button" className="btn" onClick={()=>setConfirming("")}>{labels.close}</button></form>}{message&&<p className="muted" role="status">{message}</p>}</div></div>;
}
function SuperAdmin({user,data,refresh,onLogout,language,setLanguage}:{user:User;data:any;refresh:()=>void;onLogout:()=>void;language:string;setLanguage:(v:string)=>void}){const labels=useMessages();const pendingRegistrations=(data?.registrations||[]).filter((r:any)=>r.status==="pending");return <div className="shell"><aside className="sidebar"><div className="brand"><img src="/ai-faq-logo.png" alt="AI FAQ College Chat Bot" className="brand-logo"/><span className="brand-text"><span className="brand-name">AI FAQ</span><span className="brand-sub">Super Admin</span></span></div><a href="#pending-approvals">Pending approvals ({data?.pending||0})</a><a href="#colleges">Colleges</a><a href="#providers">{labels.providers}</a><a href="#profile-security">{labels.profileSecurity}</a><button className="btn" onClick={onLogout}>{labels.signOut}</button></aside><main className="main"><MaintenanceBanner/><header className="top"><div style={{display:"flex",alignItems:"center",gap:"8px"}}><b style={{color:"#ffffff"}}>AI FAQ College Chat Bot</b> <span style={{color:"#a0a0a0",fontSize:"12px"}}>Super Admin</span></div><div style={{display:"flex",alignItems:"center",gap:"12px"}}><NotificationBell/><LanguagePicker language={language} onChange={setLanguage}/></div></header><section className="admin"><h1>{labels.platformOverview}</h1><div className="grid">{[["Colleges",data?.colleges||0],["Pending registrations",data?.pending||0],["Accounts",data?.users||0]].map(([n,v])=><div className="stat" key={String(n)}>{n}<strong>{v}</strong></div>)}</div><SupportView/><div id="pending-approvals" className="panel"><h2>Pending approvals</h2><DocumentReviewPanel/><div id="registrations"><h3>{labels.collegeRegistrations} ({pendingRegistrations.length})</h3>{pendingRegistrations.length?pendingRegistrations.map((r:any)=><RegistrationCard key={r.id} row={r} refresh={refresh}/>):<p className="muted">No college registrations are waiting for approval.</p>}</div></div><div id="colleges" className="panel"><h2>{labels.colleges}</h2><p className="muted">{data?.ai_cost_estimate_configured?labels.estimatedAiCost:labels.costEstimateNeedsRates}</p>{(data?.all_colleges||[]).map((c:any)=><div key={c.id} className="history-row"><span>{c.name} · {c.code} · {c.status} · {labels.monthlyTokens}: {c.monthly_ai_tokens||0} · {labels.estimatedAiCost}: USD {Number(c.monthly_ai_cost_usd||0).toFixed(4)}</span><QuotaEditor college={c} refresh={refresh}/><button className="btn" onClick={async()=>{if(c.status==="approved"&&confirm("Disable this college?"))await api(`/super/colleges/${c.id}`,{method:"PATCH",body:JSON.stringify({status:"disabled"})});else if(c.status!=="approved")await api(`/super/colleges/${c.id}`,{method:"PATCH",body:JSON.stringify({status:"approved"})});refresh();}}>Enable / disable</button><button className="btn" onClick={async()=>{const r=await api(`/super/colleges/${c.id}/export`);const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:"application/json"}));a.download=`college-${c.id}.json`;a.click();}}>Export</button><button className="btn" onClick={async()=>{if(confirm(`Permanently delete ${c.name}?`)){await api(`/super/colleges/${c.id}`,{method:"DELETE",body:JSON.stringify({confirm_code:String(c.id)})});refresh();}}}>Delete</button></div>)}</div><div id="providers" className="panel"><ProviderSettings/></div><div id="profile-security"><SecurityPanel user={user}/></div></section></main></div>}

function QuotaEditor({college,refresh}:{college:any;refresh:()=>void}){const keys=["pages","storage_mb","crawls_per_day","ai_tokens_month","chat_rpm","stale_data_days"];const [values,setValues]=useState<Record<string,number>>(()=>Object.fromEntries(keys.map(key=>[key,Number(college.quotas?.[key]??({pages:10000,storage_mb:1024,crawls_per_day:20,ai_tokens_month:500000,chat_rpm:60,stale_data_days:365} as Record<string,number>)[key])])));const [message,setMessage]=useState("");async function save(e:FormEvent<HTMLFormElement>){e.preventDefault();try{await api(`/super/colleges/${college.id}/settings`,{method:"PATCH",body:JSON.stringify({quotas:values})});setMessage("Saved");refresh();}catch(e:any){setMessage(e.message);}}return <form className="history-row" onSubmit={save}><label>Monthly AI tokens<input aria-label={`${college.name} monthly AI token limit`} type="number" min="0" value={values.ai_tokens_month} onChange={e=>setValues({...values,ai_tokens_month:Number(e.target.value)})}/></label><button className="mini">Save quota</button>{message&&<span className="muted">{message}</span>}</form>}

function ProviderSettings(){const [order,setOrder]=useState("gemini,xkiro"),[status,setStatus]=useState<any>(null),[message,setMessage]=useState("");async function load(){try{const data=await api("/super/ai-settings");setOrder(data.provider_order||"gemini,xkiro");setStatus(data);}catch(e:any){setMessage(e.message);}}useEffect(()=>{load();},[]);async function save(){try{await api("/super/ai-settings",{method:"PATCH",body:JSON.stringify({provider_order:order.split(",")})});setMessage("Provider order saved");await load();}catch(e:any){setMessage(e.message);}}return <div><h2>AI providers</h2><p className="muted">Provider keys stay on the server. Gemini: {status?.gemini_configured?"configured":"not configured"}{status?.providers?.gemini?.circuit_open?" · temporarily unavailable":""} · xKiro: {status?.xkiro_configured?"configured":"not configured"}{status?.providers?.xkiro?.circuit_open?" · temporarily unavailable":""}</p><label>Fallback order<select value={order} onChange={e=>setOrder(e.target.value)}><option value="gemini,xkiro">Gemini, then xKiro</option><option value="xkiro,gemini">xKiro, then Gemini</option></select></label><button className="btn" onClick={save}>Save provider order</button>{message&&<p className="muted" role="status">{message}</p>}</div>}

function SupportView(){const [collegeId,setCollegeId]=useState(""),[reason,setReason]=useState(""),[result,setResult]=useState<any>(null),[error,setError]=useState("");async function start(e:FormEvent<HTMLFormElement>){e.preventDefault();setError("");setResult(null);try{setResult(await api("/super/support-view",{method:"POST",body:JSON.stringify({college_id:Number(collegeId),reason})}));}catch(e:any){setError(e.message);}}return <section className="panel"><h2>Read-only college support</h2><form onSubmit={start}><label>College ID<input type="number" min="1" required value={collegeId} onChange={e=>setCollegeId(e.target.value)}/></label><label>Support reason<input maxLength={1000} required value={reason} onChange={e=>setReason(e.target.value)}/></label><button className="btn">Open read-only view</button></form>{error&&<p className="error">{error}</p>}{result&&<div className="panel"><p className="muted">Read-only support view · expires in {result.expires_in_minutes} minutes · access logged</p><p>Facts: {result.overview.facts} · Pages: {result.overview.pages}</p></div>}</section>}

function ChatHistory({chats,selectedId,onOpen,onRefresh,onDeleted}:{chats:Chat[];selectedId:number|null;onOpen:(chat:Chat)=>void;onRefresh:()=>void;onDeleted:(id:number)=>void}){
  const labels=useMessages();
  const [menuOpen,setMenuOpen]=useState<number|null>(null),[renameId,setRenameId]=useState<number|null>(null),[renameTitle,setRenameTitle]=useState(""),[deleteId,setDeleteId]=useState<number|null>(null),[shareLink,setShareLink]=useState(""),[error,setError]=useState("");
  const pinned=chats.filter(c=>c.pinned),unpinned=chats.filter(c=>!c.pinned);
  async function saveRename(chat:Chat,e:FormEvent<HTMLFormElement>){e.preventDefault();try{await api(`/conversations/${chat.id}`,{method:"PATCH",body:JSON.stringify({title:renameTitle})});setRenameId(null);await onRefresh();}catch(e:any){setError(e.message);}}
  async function remove(chat:Chat){try{await api(`/conversations/${chat.id}`,{method:"DELETE"});setDeleteId(null);await onRefresh();onDeleted(chat.id);}catch(e:any){setError(e.message);}}
  async function togglePin(chat:Chat){try{await api(`/conversations/${chat.id}`,{method:"PATCH",body:JSON.stringify({pinned:!chat.pinned})});await onRefresh();}catch(e:any){setError(e.message);}setMenuOpen(null);}
  async function share(chat:Chat){const link=window.location.origin+`/share/${chat.id}`;setShareLink(link);try{await navigator.clipboard?.writeText(link);}catch{}setMenuOpen(null);}
  function renderChat(chat:Chat){return <div className="history-row" key={chat.id}>{renameId===chat.id?<form className="history-rename" onSubmit={e=>saveRename(chat,e)}><input aria-label={labels.rename} value={renameTitle} onChange={e=>setRenameTitle(e.target.value)} maxLength={160} required/><button className="mini">Save</button><button type="button" className="mini" onClick={()=>setRenameId(null)}>{labels.close}</button></form>:<button className={selectedId===chat.id?"selected":""} onClick={()=>onOpen(chat)}>{chat.pinned?"📌 ":""}{chat.title}</button>}<div className="history-actions"><button className="mini" aria-label="Menu" onClick={e=>{e.stopPropagation();setMenuOpen(menuOpen===chat.id?null:chat.id)}}>&#8942;</button>{menuOpen===chat.id&&<div className="conversation-menu"><button onClick={()=>{setRenameId(chat.id);setRenameTitle(chat.title);setMenuOpen(null);}}> {labels.rename}</button><button onClick={()=>togglePin(chat)}>{chat.pinned?"Unpin":"Pin"}</button><button onClick={()=>share(chat)}>Share</button><button onClick={()=>{setDeleteId(chat.id);setMenuOpen(null);}}>{labels.delete}</button></div>}</div>{deleteId===chat.id&&<div className="conversation-menu delete-confirm"><span>{labels.chatDeleteConfirm}</span><button onClick={()=>remove(chat)}>{labels.delete}</button><button onClick={()=>setDeleteId(null)}>{labels.close}</button></div>}</div>}
  return <div className="history">{error&&<p className="error" role="alert">{error}</p>}{shareLink&&<div className="share-link"><label className="muted">Share link · select to copy</label><input readOnly value={shareLink} onFocus={e=>e.currentTarget.select()}/><button className="mini" onClick={()=>setShareLink("")}>{labels.close}</button></div>}{pinned.length>0&&<><div className="history-group">Pinned</div>{pinned.map(renderChat)}</>}{groupChatsByIstDate(unpinned,labels).map(([group,items])=><section key={group}><div className="history-group">{group}</div>{items.map(renderChat)}</section>)}</div>;
}
function DocumentReviewPanel(){
  const [documents,setDocuments]=useState<any[]>([]),[selected,setSelected]=useState<any>(null),[error,setError]=useState(""),[message,setMessage]=useState(""),[loading,setLoading]=useState(true);
  async function load(){setLoading(true);try{const result=await api("/super-admin/pending-documents");setDocuments(result.documents||[]);setError("");}catch(e:any){setError(e.message);}finally{setLoading(false);}}
  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(),15000);return()=>window.clearInterval(timer);},[]);
  async function reviewDocument(id:number){try{setSelected(await api(`/super-admin/documents/${id}`));setMessage("");}catch(e:any){setError(e.message);}}
  async function editRow(row:any){const value=window.prompt("Edit proposed value",row.proposed_value||"");if(value===null)return;try{await api(`/super-admin/staged-rows/${row.id}?proposed_value=${encodeURIComponent(value)}`,{method:"PATCH"});if(selected)await reviewDocument(selected.id);}catch(e:any){setError(e.message);}}
  async function removeRow(row:any){if(!window.confirm("Remove this proposed row?"))return;try{await api(`/super-admin/staged-rows/${row.id}`,{method:"DELETE"});if(selected)await reviewDocument(selected.id);}catch(e:any){setError(e.message);}}
  async function approve(id:number){if(!window.confirm("Approve these staged changes for the college?"))return;try{const result=await api(`/super-admin/documents/${id}/approve`,{method:"POST"});setMessage(result.message||"Approval queued.");setSelected(null);await load();}catch(e:any){setError(e.message);}}
  async function reject(id:number){const reason=window.prompt("Reason for rejection");if(reason===null)return;try{await api(`/super-admin/documents/${id}/reject?reason=${encodeURIComponent(reason)}`,{method:"POST"});setMessage("Document rejected.");setSelected(null);await load();}catch(e:any){setError(e.message);}}
  return <section className="panel" id="document-review"><h2>Pending document approvals ({documents.length})</h2><button className="btn" onClick={()=>void load()}>Refresh pending documents</button>{error&&<p className="error" role="alert">{error}</p>}{message&&<p className="muted" role="status">{message}</p>}{loading&&!documents.length&&<p className="muted">Loading pending documents…</p>}{!loading&&!error&&!documents.length&&<p className="muted">No documents are waiting for approval.</p>}{documents.map(doc=><div className="history-row" key={doc.id}><span>{doc.college_name} · {doc.filename} · {doc.status} · {doc.summary||"Extraction in progress"}</span><button className="btn" onClick={()=>reviewDocument(doc.id)}>Review</button><button className="primary" onClick={()=>void approve(doc.id)}>Approve</button></div>)}{selected&&<div className="panel"><h3>{selected.college_name} · {selected.filename}</h3><p className="muted">{selected.submitted_by} · {selected.file_type} · {selected.file_size_bytes} bytes</p>{selected.extracted_text&&<details><summary>Source text</summary><pre className="muted" style={{whiteSpace:"pre-wrap",maxHeight:260,overflow:"auto"}}>{selected.extracted_text}</pre></details>}{Object.entries(selected.staged_rows||{}).map(([table,rows]:[string,any])=><div key={table}><h4>{table}</h4>{rows.map((row:any)=><div className="panel" key={row.id}><b>{row.proposed_value}</b><p className="muted">Page {row.page_number||"—"} · Confidence {Math.round((row.confidence||0)*100)}% · {row.snippet}</p><button className="btn" onClick={()=>editRow(row)}>Edit</button> <button className="btn" onClick={()=>removeRow(row)}>Remove</button></div>)}</div>)}{!Object.keys(selected.staged_rows||{}).length&&<p className="muted">No proposed rows are ready for review yet.</p>}<button className="primary" onClick={()=>void approve(selected.id)}>Approve</button> <button className="btn" onClick={()=>reject(selected.id)}>Reject</button></div>}</section>;
}

function RegistrationCard({row,refresh}:{row:any;refresh:()=>void}){
  const labels=useMessages();const [checks,setChecks]=useState<any>(null),[result,setResult]=useState(""),[rejecting,setRejecting]=useState(false),[reason,setReason]=useState("");
  useEffect(()=>{if(row.status==="pending")api(`/registrations/${row.id}/checks`).then(setChecks).catch(()=>{});},[row.id,row.status]);
  async function decide(action:string,rejectionReason="Review failed"){try{if(action==="approve"){const c=await api(`/registrations/${row.id}/checks`);setChecks(c);if(!c.approval_allowed){setResult("Approval blocked until all verification checks pass.");return;}}const out=await api(`/registrations/${row.id}/review`,{method:"POST",body:JSON.stringify({decision:action,reason:rejectionReason})});setRejecting(false);setResult(action==="approve"?`Admin login ${out.admin_email}; temporary password ${out.temporary_password}`:"Registration rejected.");refresh();}catch(e:any){setResult(e.message);}}
  return <div className="panel"><b>{row.name}</b> · {row.status}<p className="muted">{row.website} · {row.contact_email}</p>{checks&&<p className="muted">Email domain {checks.email_domain_matches?"✓":"×"} · Website {checks.website_reachable?"✓":"×"} · Ownership proof {checks.verification_file_matches?"✓":"×"}</p>}{row.status==="pending"&&<><button className="primary" onClick={()=>decide("approve")}>{labels.approve}</button> <button className="btn" onClick={()=>setRejecting(!rejecting)}>{labels.reject}</button>{rejecting&&<form onSubmit={e=>{e.preventDefault();decide("reject",reason||"Review failed");}}><input aria-label="Rejection reason" placeholder="Reason for rejecting" value={reason} onChange={e=>setReason(e.target.value)}/><button className="btn">{labels.reject}</button><button type="button" className="mini" onClick={()=>setRejecting(false)}>{labels.close}</button></form>}</>}{result&&<p className="muted" role="status">{result}</p>}</div>;
}
function SecurityPanel({user}:{user:User}){
  const labels=useMessages();
  const [sessions,setSessions]=useState<any[]>([]),[enabled,setEnabled]=useState(!!user.mfa_enabled),[displayName,setDisplayName]=useState(user.name),[password,setPassword]=useState(""),[message,setMessage]=useState("");
  async function load(){setSessions(await api("/auth/sessions"));}
  useEffect(()=>{load().catch(()=>{});},[]);
  async function saveProfile(e:FormEvent<HTMLFormElement>){e.preventDefault();try{const result=await api("/account/profile",{method:"PATCH",body:JSON.stringify({name:displayName})});user.name=result.name;setDisplayName(result.name);setMessage(labels.profileSaved);}catch(e:any){setMessage(e.message);}}
  async function toggle(){if(!password)return;try{const result=await api("/auth/mfa",{method:"PATCH",body:JSON.stringify({enabled:!enabled,password})});setEnabled(result.enabled);setPassword("");setMessage(result.message);}catch(e:any){setMessage(e.message);}}
  return <section id="profile-security" className="panel profile-security"><h2>{labels.profileSecurity}</h2><h3>{labels.profileName}</h3><p className="muted">{labels.email}: {user.email} · Role: {user.role}{user.college_id?` · College ID: ${user.college_id}`:""}</p><form onSubmit={saveProfile}><input aria-label={labels.profileName} value={displayName} onChange={e=>setDisplayName(e.target.value)} maxLength={160} required/><button className="primary">{labels.saveProfile}</button></form><h3>{labels.changePassword}</h3><ChangePasswordInline/><h3>{labels.profileSecurity}</h3><p className="muted">{labels.emailTwoStep} {enabled?labels.enabled:labels.disabled}</p><input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder={labels.currentPassword}/><button className="btn" onClick={toggle}>{enabled?labels.disableTwoStep:labels.enableTwoStep}</button><h3>{labels.sessions}</h3>{sessions.map(s=><div className="history-row" key={s.id}>{s.device} · {new Date(s.expires_at).toLocaleString("en-IN",{timeZone:"Asia/Kolkata"})} · {s.active?labels.active:labels.signedOut}{s.active&&<button className="btn" onClick={async()=>{await api(`/auth/sessions/${s.id}`,{method:"DELETE"});await load();}}>{labels.signOutDevice}</button>}</div>)}{message&&<p className="muted" role="status">{message}</p>}</section>;
}

function CollegeAdmin({user,data,refresh,onLogout,language,setLanguage}:{user:User;data:any;refresh:()=>void;onLogout:()=>void;language:string;setLanguage:(v:string)=>void}){const labels=useMessages();const [activeSection,setActiveSection]=useState("dashboard"),[facts,setFacts]=useState<any[]>([]),[gaps,setGaps]=useState<any[]>([]),[crawls,setCrawls]=useState<any[]>([]),[conflicts,setConflicts]=useState<any[]>([]),[enquiries,setEnquiries]=useState<any[]>([]),[feedbackRows,setFeedbackRows]=useState<any[]>([]);async function load(){setFacts(await api("/admin/facts"));setGaps(await api("/admin/knowledge-gaps"));setCrawls(await api("/admin/crawls"));setConflicts(await api("/admin/conflicts"));setEnquiries(await api("/admin/enquiries"));setFeedbackRows(await api("/admin/feedback"));}useEffect(()=>{load();const timer=setInterval(()=>api("/admin/crawls").then(setCrawls).catch(()=>{}),5000);return()=>clearInterval(timer);},[]);const canEdit=user.role!=="viewer";return <div className="shell"><aside className="sidebar"><div className="brand"><img src="/ai-faq-logo.png" alt="AI FAQ College Chat Bot" className="brand-logo"/><span className="brand-text"><span className="brand-name">{data?.college ? `${data.college} Admin` : "Admin"}</span><span className="brand-sub">College Chat Bot</span></span></div><button className={`btn ${activeSection==="dashboard"?"active":""}`} onClick={()=>setActiveSection("dashboard")}>{labels.dashboard}</button><button className={`btn ${activeSection==="facts"?"active":""}`} onClick={()=>setActiveSection("facts")}>{labels.knowledgeTables}</button><button className={`btn ${activeSection==="conflicts"?"active":""}`} onClick={()=>setActiveSection("conflicts")}>{labels.conflicts}</button><button className={`btn ${activeSection==="ingestion"?"active":""}`} onClick={()=>setActiveSection("ingestion")}>{labels.ingestion}</button><button className={`btn ${activeSection==="gaps"?"active":""}`} onClick={()=>setActiveSection("gaps")}>{labels.knowledgeGaps}</button><button className={`btn ${activeSection==="members"?"active":""}`} onClick={()=>setActiveSection("members")}>{labels.members}</button><button className={`btn ${activeSection==="analytics"?"active":""}`} onClick={()=>setActiveSection("analytics")}>{labels.analytics}</button><button className={`btn ${activeSection==="widget"?"active":""}`} onClick={()=>setActiveSection("widget")}>{labels.widgetQuotas}</button><button className={`btn ${activeSection==="profile-security"?"active":""}`} onClick={()=>setActiveSection("profile-security")}>{labels.profileSecurity}</button><button className="btn" onClick={onLogout}>{labels.signOut}</button></aside><main className="main"><MaintenanceBanner/><header className="top"><div style={{display:"flex",alignItems:"center",gap:"8px"}}><b style={{color:"#ffffff"}}>{data?.college ? `${data.college} Admin` : "Admin Dashboard"}</b> <span className="badge">● Verified · Official Website</span></div><div style={{display:"flex",alignItems:"center",gap:"12px"}}><NotificationBell/><LanguagePicker language={language} onChange={setLanguage}/></div></header>{activeSection==="profile-security"&&<section className="admin"><SecurityPanel user={user}/></section>}{activeSection==="dashboard"&&<section className="admin"><h1>{data?.college ? `${data.college} Admin` : labels.dashboard}</h1><p className="muted">Institution ID: {data?.institution_id||"—"} · {labels.officialWebsite}: {data?.primary_source||"—"}</p><div className="grid">{[[labels.facts,data?.facts||0],[labels.pagesCrawled,data?.pages||0],[labels.unansweredWeek,data?.knowledge_gaps||0],[labels.questionsToday,data?.questions_today||0]].map(([n,v])=><div className="stat" key={String(n)}>{n}<strong>{v}</strong></div>)}</div>{user.role==="college_admin"&&<LocationSettings college={data} refresh={refresh}/>}<div className="panel"><h3>{labels.evidencePriority}</h3><p className="muted">{(data?.evidence_priority||[]).join(" → ")}</p><p className="muted">{labels.lastCrawl}: {data?.last_crawl?`${data.last_crawl.status} · ${data.last_crawl.pages_done}/${data.last_crawl.pages_found} · ${data.last_crawl.created_at?new Date(data.last_crawl.created_at).toLocaleString("en-IN",{timeZone:"Asia/Kolkata"}):""}`:labels.notAvailableYet}</p></div>{canEdit&&<FactEditor refresh={async()=>{await load();refresh();}}/>}</section>}{activeSection==="facts"&&<section className="panel"><h2>{labels.knowledgeData}</h2><FactDataTools editable={canEdit} onDone={async()=>{await load();refresh();}}/>{facts.map((f:any)=><FactRow key={f.id} fact={f} canEdit={canEdit} isAdmin={user.role==="college_admin"} onChanged={async()=>{await load();refresh();}}/>)}{canEdit&&<CustomFieldEditor/>}</section>}{activeSection==="conflicts"&&<section className="panel"><h2>{labels.sourceConflicts}</h2>{!conflicts.length&&<p className="muted">{labels.noConflicts}</p>}{conflicts.map((conflict:any)=><div className="panel" key={`${conflict.category}:${conflict.title}`}><h3>{conflict.title} · {conflict.category}</h3>{conflict.candidates.map((candidate:any)=><div className="history-row" key={candidate.id}><span>{candidate.value}<br/><small className="muted">{candidate.source}</small></span>{user.role==="college_admin"&&<button className="btn" onClick={async()=>{await api("/admin/conflicts/resolve",{method:"POST",body:JSON.stringify({title:conflict.title,category:conflict.category,selected_fact_id:candidate.id})});await load();refresh();}}>{labels.useThisValue}</button>}</div>)}</div>)}</section>}{activeSection==="ingestion"&&<section className="panel"><h2>{labels.websiteCrawl}</h2>{canEdit&&<><CrawlPanel onStarted={load} canSchedule={user.role==="college_admin"}/><UploadPanel onDone={load}/>{user.role==="college_admin"&&<SourcePanel/>}</>}<h3>{labels.crawlHistory}</h3>{crawls.map(j=><div className="history-row" key={j.id}>{j.status} · {j.pages_done}/{j.pages_found} pages · failed {j.pages_failed}{canEdit&&j.status==="failed"&&<button className="btn" onClick={async()=>{await api(`/admin/crawls/${j.id}/restart`,{method:"POST"});load();}}>{labels.resume}</button>}{canEdit&&["queued","running"].includes(j.status)&&<button className="btn" onClick={async()=>{await api(`/admin/crawls/${j.id}/stop`,{method:"POST"});load();}}>{labels.stopCrawl}</button>}{canEdit&&j.status==="stopped"&&<button className="btn" onClick={async()=>{await api(`/admin/crawls/${j.id}/restart`,{method:"POST"});load();}}>{labels.resume}</button>}</div>)}</section>}{activeSection==="gaps"&&<section className="panel"><h2>Knowledge gaps</h2>{gaps.map(g=><GapCard key={g.id} gap={g} onAnswered={load} editable={canEdit}/>)}</section>}{activeSection==="members"&&<section className="panel"><h2>{labels.teamInvites}</h2>{user.role==="college_admin"&&<><InviteForm/><MemberList/></>}</section>}{activeSection==="analytics"&&<section className="panel"><AnalyticsPanel/></section>}{activeSection==="widget"&&<section className="panel"><h2>{labels.widgetFeatureSettings}</h2>{user.role==="college_admin"&&<WidgetSettings/>}<UsagePanel/></section>}<section className="panel"><h2>{labels.feedbackReview}</h2><FeedbackReview items={feedbackRows} editable={canEdit} onResolved={load}/></section><section className="panel"><h2>{labels.contactOffice}</h2>{enquiries.map(e=><div className="history-row" key={e.id}><span>{e.name} · {e.email} · {e.phone} · {e.message}</span></div>)}</section><NotificationPanel/></main></div>}

function LocationSettings({college,refresh}:{college:any;refresh:()=>void}){const labels=useMessages();const [address,setAddress]=useState(college?.address||""),[latitude,setLatitude]=useState(college?.latitude??""),[longitude,setLongitude]=useState(college?.longitude??""),[message,setMessage]=useState("");async function save(e:FormEvent<HTMLFormElement>){e.preventDefault();try{await api("/admin/college-location",{method:"PATCH",body:JSON.stringify({address,latitude:latitude===""?null:Number(latitude),longitude:longitude===""?null:Number(longitude)})});setMessage(labels.saved);refresh();}catch(e:any){setMessage(e.message);}}return <form className="panel" onSubmit={save}><h3>{labels.campusLocation}</h3><input value={address} onChange={e=>setAddress(e.target.value)} placeholder={labels.address} maxLength={2000}/><div className="grid"><label>{labels.latitude}<input type="number" step="any" min="-90" max="90" value={latitude} onChange={e=>setLatitude(e.target.value)}/></label><label>{labels.longitude}<input type="number" step="any" min="-180" max="180" value={longitude} onChange={e=>setLongitude(e.target.value)}/></label></div><button className="primary">{labels.saveLocation}</button><span className="muted"> {message}</span></form>}

function NotificationBell(){
  const labels=useMessages();
  const [open,setOpen]=useState(false);
  const [items,setItems]=useState<any[]>([]);
  const [error,setError]=useState("");
  const popoverRef=useRef<HTMLDivElement>(null);
  const btnRef=useRef<HTMLButtonElement>(null);

  async function load(){
    try{
      const data=await api("/admin/notifications");
      setItems(Array.isArray(data)?data:[]);
      setError("");
    }catch(e:any){
      setError(e.message);
    }
  }

  useEffect(()=>{
    load();
    const timer=setInterval(load,15000);
    return()=>clearInterval(timer);
  },[]);

  useEffect(()=>{
    function handleOutside(e:MouseEvent){
      if(popoverRef.current&&!popoverRef.current.contains(e.target as Node)&&
         btnRef.current&&!btnRef.current.contains(e.target as Node)){
        setOpen(false);
      }
    }
    function handleKeyDown(e:globalThis.KeyboardEvent){
      if(e.key==="Escape") setOpen(false);
    }
    if(open){
      document.addEventListener("mousedown",handleOutside);
      window.addEventListener("keydown",handleKeyDown);
    }
    return ()=>{
      document.removeEventListener("mousedown",handleOutside);
      window.removeEventListener("keydown",handleKeyDown);
    };
  },[open]);

  async function markRead(id:number){
    try{
      await api(`/admin/notifications/${id}/read`,{method:"PATCH"});
      await load();
    }catch(e:any){
      setError(e.message);
    }
  }

  async function markAllRead(){
    try{
      await api("/admin/notifications/read-all",{method:"POST"});
      await load();
    }catch(e:any){
      setError(e.message);
    }
  }

  const unreadCount = items.filter(x=>!x.read).length;

  return (
    <div style={{position:"relative",display:"inline-block"}}>
      <button
        ref={btnRef}
        type="button"
        aria-label="Notifications"
        title="Notifications"
        onClick={()=>setOpen(o=>!o)}
        style={{
          position:"relative",
          background:open?"#222222":"#141414",
          border:"1px solid #2e2e2e",
          borderRadius:"9px",
          width:"38px",
          height:"38px",
          display:"flex",
          alignItems:"center",
          justifyContent:"center",
          cursor:"pointer",
          color:unreadCount>0?"#ffffff":"#a0a0a0",
          transition:"background 0.15s, border-color 0.15s",
          padding:0
        }}
        onMouseEnter={e=>{e.currentTarget.style.borderColor="#444";e.currentTarget.style.color="#fff";}}
        onMouseLeave={e=>{e.currentTarget.style.borderColor="#2e2e2e";if(!open&&unreadCount===0)e.currentTarget.style.color="#a0a0a0";}}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount>0&&(
          <span style={{
            position:"absolute",
            top:"-4px",
            right:"-4px",
            background:"#ef4444",
            color:"#ffffff",
            fontSize:"10px",
            fontWeight:700,
            borderRadius:"999px",
            minWidth:"18px",
            height:"18px",
            padding:"0 4px",
            display:"flex",
            alignItems:"center",
            justifyContent:"center",
            boxShadow:"0 2px 8px rgba(239,68,68,0.5)",
            border:"1px solid #000000"
          }}>
            {unreadCount>99?"99+":unreadCount}
          </span>
        )}
      </button>

      {open&&(
        <div
          ref={popoverRef}
          style={{
            position:"absolute",
            top:"46px",
            right:0,
            width:"360px",
            maxWidth:"calc(100vw - 32px)",
            background:"#111111",
            border:"1px solid #2a2a2a",
            borderRadius:"14px",
            boxShadow:"0 16px 48px rgba(0,0,0,0.85)",
            zIndex:1000,
            display:"flex",
            flexDirection:"column",
            overflow:"hidden"
          }}
        >
          {/* Popover Header */}
          <div style={{
            padding:"13px 16px",
            borderBottom:"1px solid #202020",
            display:"flex",
            alignItems:"center",
            justifyContent:"space-between",
            background:"#151515"
          }}>
            <div style={{display:"flex",alignItems:"center",gap:"8px"}}>
              <span style={{fontWeight:700,fontSize:"14px",color:"#ffffff"}}>Notifications</span>
              {unreadCount>0&&(
                <span style={{
                  background:"rgba(239,68,68,0.15)",
                  color:"#fca5a5",
                  fontSize:"11px",
                  fontWeight:600,
                  padding:"1px 7px",
                  borderRadius:"999px",
                  border:"1px solid rgba(239,68,68,0.3)"
                }}>
                  {unreadCount} new
                </span>
              )}
            </div>
            <div style={{display:"flex",alignItems:"center",gap:"6px"}}>
              {unreadCount>0&&(
                <button
                  type="button"
                  onClick={markAllRead}
                  style={{
                    background:"transparent",
                    border:"none",
                    color:"#a0a0a0",
                    fontSize:"11px",
                    cursor:"pointer",
                    padding:"3px 6px",
                    borderRadius:"4px"
                  }}
                  onMouseEnter={e=>e.currentTarget.style.color="#ffffff"}
                  onMouseLeave={e=>e.currentTarget.style.color="#a0a0a0"}
                >
                  Mark all read
                </button>
              )}
              <button
                type="button"
                onClick={()=>setOpen(false)}
                style={{
                  background:"transparent",
                  border:"none",
                  color:"#888",
                  fontSize:"16px",
                  cursor:"pointer",
                  padding:"0 4px",
                  lineHeight:1
                }}
                aria-label="Close"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Notifications List */}
          <div style={{maxHeight:"380px",overflowY:"auto"}}>
            {error&&<p style={{margin:"12px 16px",color:"#fca5a5",fontSize:"12px"}}>{error}</p>}
            {items.length===0&&!error?(
              <div style={{padding:"36px 16px",textAlign:"center",color:"#666"}}>
                <div style={{fontSize:"30px",marginBottom:"8px",opacity:0.4}}>🔔</div>
                <p style={{margin:"0 0 3px",fontSize:"13px",fontWeight:600,color:"#888"}}>No notifications</p>
                <p style={{margin:0,fontSize:"11px",color:"#555"}}>You are all caught up!</p>
              </div>
            ):(
              items.map(item=>(
                <div
                  key={item.id}
                  style={{
                    padding:"12px 16px",
                    borderBottom:"1px solid #1c1c1c",
                    background:!item.read?"rgba(255,255,255,0.025)":"transparent",
                    borderLeft:!item.read?"3px solid #ef4444":"3px solid transparent",
                    display:"flex",
                    flexDirection:"column",
                    gap:"4px"
                  }}
                >
                  <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:"8px"}}>
                    <span style={{fontSize:"13px",fontWeight:!item.read?700:500,color:"#ffffff",lineHeight:1.35}}>
                      {item.title}
                    </span>
                    {!item.read&&(
                      <button
                        type="button"
                        onClick={()=>markRead(item.id)}
                        style={{
                          background:"#1c1c1c",
                          border:"1px solid #2e2e2e",
                          color:"#a0a0a0",
                          borderRadius:"6px",
                          padding:"2px 8px",
                          fontSize:"11px",
                          cursor:"pointer",
                          whiteSpace:"nowrap",
                          flexShrink:0
                        }}
                        onMouseEnter={e=>{e.currentTarget.style.color="#fff";e.currentTarget.style.borderColor="#444";}}
                        onMouseLeave={e=>{e.currentTarget.style.color="#a0a0a0";e.currentTarget.style.borderColor="#2e2e2e";}}
                      >
                        Mark read
                      </button>
                    )}
                  </div>
                  {item.body&&(
                    <p style={{margin:0,fontSize:"12px",color:"#999999",lineHeight:1.45}}>
                      {item.body}
                    </p>
                  )}
                  <span style={{fontSize:"10px",color:"#555555",marginTop:"2px"}}>
                    {item.created_at?new Date(item.created_at).toLocaleString("en-IN",{timeZone:"Asia/Kolkata"}):""}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function NotificationPanel(){ return null; }

function FeedbackReview({items,editable,onResolved}:{items:any[];editable:boolean;onResolved:()=>void}){const labels=useMessages();const [error,setError]=useState("");async function resolve(id:number,action:string,form?:HTMLFormElement){let body:any={action};if(action==="correct"&&form){const d=new FormData(form);body={...body,category:d.get("category"),title:d.get("title"),value:d.get("value")};}try{await api(`/admin/feedback/${id}/resolve`,{method:"POST",body:JSON.stringify(body)});onResolved();}catch(e:any){setError(e.message);}}if(!items.length)return <p className="muted">{labels.noFeedback}</p>;return <div>{items.map(item=><div className="panel" key={item.id}><p><b>{labels.question}:</b> {item.question}</p><p><b>{labels.reportedAnswer}:</b> {item.answer}</p>{item.reason&&<p className="muted">{labels.reportReason}: {item.reason}</p>}{editable&&<><form onSubmit={e=>{e.preventDefault();resolve(item.id,"correct",e.currentTarget);}}><input name="category" defaultValue="general" placeholder={labels.category} required/><input name="title" defaultValue={item.question} placeholder={labels.factTitle} required/><textarea name="value" placeholder={labels.verifiedCorrection} required/><button className="primary">{labels.saveCorrection}</button></form><button className="btn" onClick={()=>resolve(item.id,"dismiss")}>{labels.dismiss}</button></>}</div>)}{error&&<p className="error">{error}</p>}</div>}

function FactEditor({refresh}:{refresh:()=>void}){
  const labels=useMessages();const [message,setMessage]=useState("");
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const form=e.currentTarget;const data=new FormData(form);try{const result=await api("/admin/facts",{method:"POST",body:JSON.stringify({category:data.get("category"),title:data.get("title"),value:data.get("value"),academic_year:data.get("academic_year")||null,valid_from:data.get("valid_from")||null,valid_to:data.get("valid_to")||null})});form.reset();setMessage(result.message||"Fact saved and available in chat.");refresh();}catch(e:any){setMessage(e.message);}}
  return <form className="panel" onSubmit={submit}><h3>{labels.addVerifiedInfo}</h3><input name="category" placeholder={labels.category} maxLength={100} required/><input name="title" placeholder={labels.factTitle} maxLength={300} required/><textarea name="value" placeholder={labels.evidenceValue} maxLength={50000} required/><input name="academic_year" placeholder={labels.academicYear}/><div className="grid"><label>{labels.validFrom}<input name="valid_from" type="date"/></label><label>{labels.validUntil}<input name="valid_to" type="date"/></label></div><button className="primary">{labels.saveFact}</button>{message&&<p className="muted" role="status">{message}</p>}</form>;
}

function FactDataTools({editable,onDone}:{editable:boolean;onDone:()=>void}){
  const labels=useMessages();const [message,setMessage]=useState("");
  async function exportFacts(format:"csv"|"xlsx"){try{const response=await fetch(getApiBase()+`/admin/facts/export?format=${format}`,{credentials:"include"});if(!response.ok){const raw=await response.text();throw new Error(raw||response.statusText);}const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=format==="csv"?"college-facts.csv":"college-facts.xlsx";link.click();URL.revokeObjectURL(url);}catch(e:any){setMessage(e.message);}}
  async function importFacts(e:FormEvent<HTMLFormElement>){e.preventDefault();const form=e.currentTarget;const input=form.elements.namedItem("file") as HTMLInputElement;const file=input.files?.[0];if(!file)return;const body=new FormData();body.set("file",file);try{const result=await api("/admin/facts/import",{method:"POST",body});setMessage(result.message||"Facts imported.");form.reset();onDone();}catch(e:any){setMessage(e.message);}}
  return <div className="panel"><button type="button" className="btn" onClick={()=>exportFacts("csv")}>{labels.exportCsv}</button> <button type="button" className="btn" onClick={()=>exportFacts("xlsx")}>{labels.exportExcel}</button>{editable&&<form onSubmit={importFacts}><label>{labels.importFacts}<input name="file" type="file" accept=".csv,.xlsx" required/></label><button className="btn">{labels.importFacts}</button></form>}{message&&<p className="muted" role="status">{message}</p>}</div>;
}

function FactRow({fact,canEdit,isAdmin,onChanged}:{fact:any;canEdit:boolean;isAdmin:boolean;onChanged:()=>void}){
  const labels=useMessages();
  const [history,setHistory]=useState<any[]|null>(null),[error,setError]=useState(""),[editing,setEditing]=useState(false),[editValue,setEditValue]=useState(fact.value),[confirmDelete,setConfirmDelete]=useState(false);
  async function toggle(){if(history!==null){setHistory(null);return;}try{setHistory(await api(`/admin/facts/${fact.id}/history`));}catch(e:any){setError(e.message);}}
  async function save(e:FormEvent<HTMLFormElement>){e.preventDefault();try{await api(`/admin/facts/${fact.id}`,{method:"PATCH",body:JSON.stringify({category:fact.category,title:fact.title,value:editValue,extra:fact.extra||{}})});setEditing(false);await onChanged();}catch(e:any){setError(e.message);}}
  async function remove(){try{await api(`/admin/facts/${fact.id}`,{method:"DELETE"});setConfirmDelete(false);await onChanged();}catch(e:any){setError(e.message);}}
  async function restore(id:number){try{await api(`/admin/facts/${fact.id}/restore/${id}`,{method:"POST"});await onChanged();setHistory(await api(`/admin/facts/${fact.id}/history`));}catch(e:any){setError(e.message);}}
  return <div className="panel"><div className="history-row"><span><b>{fact.title}</b> · {fact.category}: {fact.value}</span>{canEdit&&<><button className="btn" onClick={()=>{setEditValue(fact.value);setEditing(true);}}>Edit</button><button className="btn" onClick={()=>setConfirmDelete(true)}>{labels.delete}</button></>}<button className="btn" onClick={toggle}>{history===null?labels.viewHistory:labels.hideHistory}</button></div>{editing&&<form onSubmit={save}><textarea aria-label="Edit fact value" value={editValue} onChange={e=>setEditValue(e.target.value)} required rows={4}/><button className="primary">Save</button><button type="button" className="btn" onClick={()=>setEditing(false)}>{labels.close}</button></form>}{confirmDelete&&<div className="panel"><p>{labels.deleteHistory}?</p><button className="btn" onClick={remove}>{labels.delete}</button><button className="btn" onClick={()=>setConfirmDelete(false)}>{labels.close}</button></div>}{error&&<p className="error">{error}</p>}{history&&(!history.length?<p className="muted">{labels.noHistory}</p>:history.map(h=><div className="history-row" key={h.id}><span>{h.value}<br/><small className="muted">{h.changed_via} · {new Date(h.created_at).toLocaleString("en-IN",{timeZone:"Asia/Kolkata"})}</small></span>{isAdmin&&<button className="btn" onClick={()=>restore(h.id)}>{labels.restore}</button>}</div>))}</div>;
}
function GapCard({gap,onAnswered,editable}:{gap:any;onAnswered:()=>void;editable:boolean}){
  const labels=useMessages();const [answer,setAnswer]=useState(""),[open,setOpen]=useState(false),[msg,setMsg]=useState("");
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();try{await api(`/admin/knowledge-gaps/${gap.id}/answer`,{method:"POST",body:JSON.stringify({title:gap.question,value:answer,category:"general"})});setMsg("Saved");setAnswer("");setOpen(false);onAnswered();}catch(e:any){setMsg(e.message);}}
  return <div className="history-row"><span>{gap.question} · asked {gap.count} times</span>{editable&&<button className="btn" onClick={()=>setOpen(!open)}>{labels.provideAnswer}</button>}{msg&&<span className="muted">{msg}</span>}{open&&<form className="panel" onSubmit={submit}><textarea aria-label={labels.provideAnswer} value={answer} onChange={e=>setAnswer(e.target.value)} required rows={3}/><button className="primary">Save</button><button type="button" className="btn" onClick={()=>setOpen(false)}>{labels.close}</button></form>}</div>;
}
function CrawlPanel({onStarted,canSchedule}:{onStarted:()=>void;canSchedule:boolean}){const labels=useMessages();const [url,setUrl]=useState(""),[msg,setMsg]=useState(""),[scheduled,setScheduled]=useState(false);useEffect(()=>{api("/admin/crawl-schedule").then(s=>{setScheduled(!!s.enabled);if(s.url)setUrl(s.url);}).catch(()=>{});},[]);async function start(){try{const j=await api("/admin/crawl",{method:"POST",body:JSON.stringify({url})});setMsg(`Crawl ${j.status} · job ${j.id}`);onStarted();}catch(e:any){setMsg(e.message);}}async function toggleSchedule(){try{const result=await api("/admin/crawl-schedule",{method:"PUT",body:JSON.stringify({enabled:!scheduled,url,interval_days:7})});setScheduled(result.enabled);setMsg(result.enabled?"Weekly crawl scheduled":"Scheduled crawl stopped");}catch(e:any){setMsg(e.message);}}return <div><input type="url" value={url} onChange={e=>setUrl(e.target.value)} placeholder={labels.registeredHttps}/><button className="primary" onClick={start}>{labels.startCrawl}</button>{canSchedule&&<button className="btn" onClick={toggleSchedule}>{scheduled?labels.stopWeekly:labels.scheduleWeekly}</button>}<span className="muted"> {msg}</span></div>}
function UploadPanel({onDone}:{onDone:()=>void}){
  const labels=useMessages();const [file,setFile]=useState<File|null>(null),[msg,setMsg]=useState(""),[busy,setBusy]=useState(false),[progress,setProgress]=useState(0),[refresh,setRefresh]=useState(0);
  async function upload(){if(!file||busy)return;const body=new FormData();body.set("file",file);const isImage=/\.(png|jpg|jpeg|webp|gif)$/i.test(file.name);setBusy(true);setProgress(0);setMsg("Uploading…");
    try{const result=await new Promise<any>((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open("POST",getApiBase()+(isImage?"/admin/media":"/admin/document-upload"));xhr.withCredentials=true;xhr.upload.onprogress=e=>{if(e.lengthComputable)setProgress(Math.round(e.loaded/e.total*100));};xhr.onerror=()=>reject(new Error("The Admin API connection failed before an HTTP response. Check that port 8001 is reachable and inspect the Admin backend log for this request ID."));xhr.ontimeout=()=>reject(new Error("Upload timed out. Retry with a smaller file or check the Admin backend."));xhr.timeout=120000;xhr.onload=()=>{let data:any={};try{data=JSON.parse(xhr.responseText||"{}");}catch{}if(xhr.status<200||xhr.status>=300){const messages:Record<number,string>={401:"Not signed in to the Admin Side (401).",403:"This Admin account cannot upload for its college (403).",404:"Admin upload endpoint was not found (404).",413:"File exceeds the 20 MB upload limit (413).",422:"PDF or document is invalid or unreadable (422).",500:"Admin backend failed while saving the upload (500)."};reject(new Error(messages[xhr.status]||data.detail||`${xhr.status}: ${xhr.statusText}`));}else resolve(data);};xhr.send(body);});
      setMsg(isImage?"Image stored in media library":`Upload complete. Extraction and staging started (${result.status||"pending review"}).`);setFile(null);setRefresh(v=>v+1);onDone();
    }catch(e:any){setMsg(e.message||"Upload failed");}finally{setBusy(false);}}
  return <div className="panel"><h3>{labels.smartUpload}</h3><input type="file" accept=".pdf,.docx,.xlsx,.xlsm,.png,.jpg,.jpeg,.webp,.gif" disabled={busy} onChange={e=>setFile(e.target.files?.[0]||null)}/><button className="primary" onClick={upload} disabled={!file||busy}>{busy?`Uploading ${progress}%…`:labels.uploadIndex}</button>{busy&&<progress max="100" value={progress} aria-label="Upload progress"/>}<span className="muted"> {msg}</span><DocumentStatusList key={refresh}/></div>
}

function DocumentStatusList(){const [documents,setDocuments]=useState<any[]>([]),[error,setError]=useState("");useEffect(()=>{api("/admin/documents").then(result=>setDocuments(result.documents||[])).catch((e:any)=>setError(e.message));},[]);return <div><h4>Uploaded documents</h4>{error&&<p className="error">{error}</p>}{documents.map(doc=><p className="muted" key={doc.id}>{doc.filename} · {doc.status==="pending"?"PENDING_REVIEW":doc.status}{doc.summary?` · ${doc.summary}`:""}{doc.reject_reason?` · ${doc.reject_reason}`:""}</p>)}</div>}
function CustomFieldEditor(){const labels=useMessages();const [table,setTable]=useState("other_facts"),[field,setField]=useState(""),[msg,setMsg]=useState("");async function save(){try{await api("/admin/custom-fields",{method:"POST",body:JSON.stringify({table_name:table,field_name:field,field_type:"text"})});setMsg("Field added to flexible data schema");}catch(e:any){setMsg(e.message);}}return <div className="panel"><h3>{labels.customDataField}</h3><input value={table} onChange={e=>setTable(e.target.value)} placeholder={labels.tableCategory}/><input value={field} onChange={e=>setField(e.target.value)} placeholder={labels.fieldName}/><button className="btn" onClick={save}>{labels.addField}</button><span className="muted"> {msg}</span></div>}
function SourcePanel(){
  const labels=useMessages();
  const [url,setUrl]=useState(""),[sourceType,setSourceType]=useState("department site"),[priority,setPriority]=useState(2),[campus,setCampus]=useState(""),[sources,setSources]=useState<any[]>([]),[msg,setMsg]=useState("");
  async function load(){setSources(await api("/admin/sources"));}
  useEffect(()=>{load().catch((e:any)=>setMsg(e.message));},[]);
  async function save(){try{await api("/admin/sources",{method:"POST",body:JSON.stringify({url,type:sourceType,priority,campus})});setUrl("");setMsg("Source added");await load();}catch(e:any){setMsg(e.message);}}
  async function remove(id:number){try{await api(`/admin/sources/${id}`,{method:"DELETE"});await load();}catch(e:any){setMsg(e.message);}}
  return <div className="panel"><h3>{labels.additionalSource}</h3><input type="url" value={url} onChange={e=>setUrl(e.target.value)} placeholder={labels.httpsSource} aria-label={labels.httpsSource}/><div className="grid"><label>{labels.sourceType}<input value={sourceType} onChange={e=>setSourceType(e.target.value)} maxLength={40}/></label><label>{labels.priority}<input type="number" min="1" max="100" value={priority} onChange={e=>setPriority(Number(e.target.value))}/></label><label>{labels.campus}<input value={campus} onChange={e=>setCampus(e.target.value)} maxLength={180}/></label></div><button className="btn" onClick={save} disabled={!url.trim()}>{labels.addSource}</button><span className="muted"> {msg}</span>{sources.map(source=><div className="history-row" key={source.id}><span>{source.url}<br/><small className="muted">{source.type} · priority {source.priority}{source.campus?` · ${source.campus}`:""}</small></span><button className="btn" onClick={()=>remove(source.id)}>{labels.removeSource}</button></div>)}</div>
}
function InviteForm(){const labels=useMessages();const [email,setEmail]=useState(""),[role,setRole]=useState("editor"),[msg,setMsg]=useState("");async function invite(){try{const r=await api("/admin/invitations",{method:"POST",body:JSON.stringify({email,role})});setMsg(`Invitation sent ${r.development_token?`(dev token ${r.development_token})`:""}`);}catch(e:any){setMsg(e.message);}}return <div><input value={email} onChange={e=>setEmail(e.target.value)} placeholder={labels.inviteEmail}/><select value={role} onChange={e=>setRole(e.target.value)}><option>editor</option><option>viewer</option><option>college_admin</option></select><button className="primary" onClick={invite}>{labels.invite}</button><p className="muted">{msg}</p></div>}
function MemberList(){const labels=useMessages();const [members,setMembers]=useState<any[]>([]),[error,setError]=useState("");async function load(){setMembers(await api("/admin/members"));}useEffect(()=>{load().catch((e:any)=>setError(e.message));},[]);async function remove(id:number){if(!confirm(labels.removeMemberConfirm))return;try{await api(`/admin/members/${id}`,{method:"DELETE"});await load();}catch(e:any){setError(e.message);}}return <div><h3>{labels.members}</h3>{members.map(m=><div className="history-row" key={m.id}><span>{m.name} · {m.email} · {m.role}</span><button className="btn" onClick={()=>remove(m.id)}>{labels.remove}</button></div>)}{error&&<p className="error">{error}</p>}</div>}
function AnalyticsPanel(){const labels=useMessages();const [data,setData]=useState<any>(null),[error,setError]=useState("");useEffect(()=>{api("/admin/analytics").then(setData).catch((e:any)=>setError(e.message));},[]);if(error)return <p className="error">{error}</p>;if(!data)return <p className="muted">{labels.working}</p>;return <div><h2>{labels.analytics}</h2><div className="grid"><div className="stat" key="questions">{labels.questionsToday}<strong>{data.questions_today}</strong></div><div className="stat" key="unanswered">{labels.unansweredWeek}<strong>{data.unanswered_week}</strong></div><div className="stat" key="satisfaction">{labels.satisfactionPercent}<strong>{data.satisfaction_percent===null?"—":`${data.satisfaction_percent}%`}</strong></div><div className="stat" key="p95">{labels.p95Response}<strong>{data.p95_response_ms===null?"—":`${data.p95_response_ms} ms`}</strong></div></div><div className="panel"><h3>{labels.questionsPerDay}</h3>{(Object.entries(data.daily||{}) as [string,any][]).map(([day,counts])=><div className="history-row" key={day}><span>{day}</span><span>{labels.questionsToday}: {counts.questions} · {labels.answered}: {counts.answered} · {labels.unanswered}: {counts.unanswered}</span></div>)}</div><div className="panel"><h3>{labels.topTopics}</h3>{data.top_topics?.length?data.top_topics.map((topic:any)=><div className="history-row" key={topic.topic}><span>{topic.topic}</span><span>{topic.count}</span></div>):<p className="muted">{labels.noDataYet}</p>}</div>{data.slow_answers?.length>0&&<div className="panel"><h3>{labels.slowAnswers}</h3>{data.slow_answers.map((row:any,i:number)=><div className="history-row" key={i}><span>{row.question}</span><span>{row.response_ms} ms</span></div>)}</div>}<p className="muted">{labels.feedbackTotal}: {data.feedback_total}</p></div>}

function UsagePanel(){const labels=useMessages();const [usage,setUsage]=useState<any>(null),[error,setError]=useState("");useEffect(()=>{api("/admin/usage").then(setUsage).catch((e:any)=>setError(e.message));},[]);if(error)return <p className="error">{error}</p>;if(!usage)return <p className="muted">{labels.working}</p>;return <div className="panel"><h3>{labels.showUsage}</h3><p>{labels.pagesCrawled}: {usage.pages}/{usage.quotas?.pages??10000} ({usage.page_percent}%)</p><p>{labels.crawlsToday}: {usage.crawls_today}/{usage.quotas?.crawls_per_day??20} ({usage.crawl_percent}%)</p><p>{labels.storageUsed}: {(usage.media_bytes/1024/1024).toFixed(1)} MB/{usage.quotas?.storage_mb??1024} MB ({usage.storage_percent}%)</p><p>{labels.aiTokensThisMonth}: {usage.ai_tokens_this_month}/{usage.quotas?.ai_tokens_month??500000} ({usage.token_percent}%)</p>{usage.alerts?.length?<p className="error">{labels.quotaAlerts}: {usage.alerts.join(" · ")}</p>:<p className="muted">{labels.noQuotaAlerts}</p>}</div>}

function WidgetSettings(){const labels=useMessages();const [domains,setDomains]=useState(""),[snippet,setSnippet]=useState(""),[flags,setFlags]=useState<any>({voice:true,widget:true,semantic_search:true});useEffect(()=>{api("/admin/widget").then(w=>{setDomains((w.allowed_domains||[]).join(", "));setFlags({voice:true,widget:true,semantic_search:true,...(w.feature_flags||{})});setSnippet(w.embed_script||"");}).catch(()=>{});},[]);async function save(){try{await api("/admin/college-settings",{method:"PATCH",body:JSON.stringify({allowed_domains:domains.split(",").map(x=>x.trim()).filter(Boolean),feature_flags:flags})});const w=await api("/admin/widget");setSnippet(w.embed_script);}catch(e:any){setSnippet(e.message);}}return <div><input aria-label={labels.allowedDomains} placeholder={labels.allowedDomains} value={domains} onChange={e=>setDomains(e.target.value)}/><fieldset className="panel"><legend>{labels.featureFlags}</legend>{([["widget",labels.widgetFeature],["voice",labels.voiceFeature],["semantic_search",labels.semanticFeature]] as [string,string][]).map(([key,label])=><label key={key} className="history-row"><span>{label}</span><input type="checkbox" checked={!!flags[key]} onChange={e=>setFlags({...flags,[key]:e.target.checked})}/></label>)}</fieldset><button className="primary" onClick={save}>{labels.saveWidget}</button>{snippet&&<pre className="muted">{snippet}</pre>}</div>}


