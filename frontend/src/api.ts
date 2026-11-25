import axios from 'axios'
import {create} from 'zustand'

type Tokens = {access:string;refresh:string}
export type Profile = {username:string;email:string;flats:{id:number;name:string;member:number;role:string}[]}
type Session = {tokens:Tokens|null;flat:number;setTokens:(value:Tokens|null)=>void;choose:(id:number)=>void}
function savedTokens(): Tokens|null {
  try {return JSON.parse(sessionStorage.getItem('broshare-session') ?? 'null')}
  catch {return null}
}
export const useSession = create<Session>(set=>({
  tokens:savedTokens(), flat:Number(sessionStorage.getItem('broshare-flat') ?? 0),
  setTokens:tokens=>{
    if(tokens) sessionStorage.setItem('broshare-session',JSON.stringify(tokens))
    else sessionStorage.removeItem('broshare-session')
    set({tokens})
  },
  choose:flat=>{sessionStorage.setItem('broshare-flat',String(flat));set({flat})},
}))
const baseURL=import.meta.env.VITE_API_BASE_URL || '/api'
const auth=axios.create({baseURL})
export const api=axios.create({baseURL})
let refresh:Promise<Tokens>|null=null
api.interceptors.request.use(config=>{
  const {tokens,flat}=useSession.getState()
  if(tokens) config.headers.Authorization='Bearer '+tokens.access
  if(flat) config.headers['X-Flat-ID']=flat
  return config
})
api.interceptors.response.use(result=>result,async error=>{
  const config=error.config
  const {tokens,setTokens}=useSession.getState()
  if(error.response?.status!==401 || !config || config.retried || !tokens) throw error
  config.retried=true
  if(config.headers.Authorization==='Bearer '+tokens.access){
    refresh ??= auth.post<Tokens>('/auth/refresh/',{refresh:tokens.refresh}).then(({data})=>{
      if(useSession.getState().tokens?.refresh===tokens.refresh) setTokens(data)
      return data
    }).catch(problem=>{
      if(axios.isAxiosError(problem) && [400,401].includes(problem.response?.status ?? 0) &&
         useSession.getState().tokens?.refresh===tokens.refresh) setTokens(null)
      throw problem
    }).finally(()=>{refresh=null})
    await refresh
  }
  if(!useSession.getState().tokens) throw error
  return api(config)
})
export async function signIn(username:string,password:string,register:boolean){
  if(register) await auth.post('/auth/register/',{username,password})
  const {data}=await auth.post<Tokens>('/auth/login/',{username,password})
  useSession.getState().setTokens(data)
}
export async function signOut(){
  const session=useSession.getState()
  try {await api.post('/auth/logout/',{refresh:session.tokens?.refresh})}
  finally {session.setTokens(null);session.choose(0)}
}
export async function list<T>(path:string,signal?:AbortSignal):Promise<T[]>{
  const out:T[]=[]
  let page=1,next=true
  while(next){
    const {data}=await api.get<{results:T[];next:string|null}>(path,{params:{page,page_size:100},signal})
    out.push(...data.results);next=Boolean(data.next);page++
  }
  return out
}
export function errorText(error:unknown):string{
  if(axios.isAxiosError(error)){
    const data=error.response?.data
    if(typeof data?.detail==='string') return data.detail
    if(data && typeof data==='object') return Object.entries(data).map(([k,v])=>k+': '+(Array.isArray(v)?v.join(' '):JSON.stringify(v))).join(' · ')
    return error.message
  }
  return error instanceof Error?error.message:'Unable to complete the request.'
}

