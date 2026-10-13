// Only public Firebase web configuration is fetched here; never service-account keys.
let firebaseAuth=null;
async function startPersonalAuth(){
  const status=document.querySelector('#authStatus');
  const retry=document.querySelector('#authRetry');
  const buttons=['sendBtn','dataSave','dataUpdate','dataDelete','analyzeRecords'];
  buttons.forEach(id=>{const b=document.getElementById(id);if(b)b.disabled=true});
  if(status)status.textContent='개인 기록을 위한 익명 인증을 연결하고 있어요…';
  try{
    const base=(window.APP_CONFIG&&window.APP_CONFIG.API_BASE_URL)||'http://127.0.0.1:8000';
    const response=await fetch(base+'/api/auth/config',{signal:AbortSignal.timeout(150000)});
    if(!response.ok)throw new Error('인증 설정을 불러오지 못했어요. 잠시 후 다시 연결해 주세요.');
    const config=await response.json();
    if(!config.enabled)throw new Error('서버의 Firebase 익명 인증 설정이 필요합니다. 공개 지역 통계는 계속 조회할 수 있어요.');
    const [appSDK,authSDK]=await Promise.all([
      import('https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js'),
      import('https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js')
    ]);
    const app=appSDK.getApps().length?appSDK.getApp():appSDK.initializeApp(config.config);
    firebaseAuth=authSDK.getAuth(app);
    await authSDK.setPersistence(firebaseAuth,authSDK.browserLocalPersistence);
    await new Promise((resolve,reject)=>{let unsubscribe=authSDK.onAuthStateChanged(firebaseAuth,()=>{unsubscribe();resolve()},reject)});
    if(!firebaseAuth.currentUser)await authSDK.signInAnonymously(firebaseAuth);
    if(status)status.textContent='개인 기록 보호가 연결됐어요. 이 브라우저의 본인 기록만 표시해요. 브라우저 정보 삭제·다른 기기에서는 기존 기록을 불러오지 못할 수 있어요.';
    if(retry)retry.hidden=true;
    ['sendBtn','dataSave','analyzeRecords'].forEach(id=>{document.getElementById(id).disabled=false});
    return firebaseAuth;
  }catch(error){
    const msg=error.code==='auth/operation-not-allowed'?'Firebase에서 익명 로그인 제공업체를 활성화해 주세요.':error.code==='auth/invalid-api-key'?'Firebase 웹 API 키 설정을 확인해 주세요.':error.code?'익명 인증 연결에 실패했어요. 설정과 네트워크를 확인한 뒤 다시 연결해 주세요.':error.message;
    if(status)status.textContent=msg;
    if(retry)retry.hidden=false;
    throw new Error(msg);
  }
}
window.personalAuth=startPersonalAuth();
window.personalAuth.catch(()=>{});
window.personalAuthHeaders=async(forceRefresh=false)=>{const auth=await window.personalAuth;return {Authorization:'Bearer '+await auth.currentUser.getIdToken(forceRefresh)}};
document.querySelector('#authRetry').onclick=()=>{
  window.personalAuth=startPersonalAuth();window.personalAuth.catch(()=>{});
  window.personalAuth.then(()=>window.reloadPrivateRecords?.()).catch(()=>{});
};
