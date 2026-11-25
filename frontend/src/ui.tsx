import {useEffect,useRef,type ReactNode} from 'react'
import {X,ArrowUpRight,Inbox} from 'lucide-react'

export type Option={value:string|number;label:string}
export function Field({label,name,type='text',value,required=true,min,step,maxLength}:{
  label:string;name:string;type?:string;value?:string|number;required?:boolean;min?:number;step?:string;maxLength?:number
}){
  return <label className="field">{label}<input name={name} type={type} defaultValue={value} required={required} min={min} step={step} maxLength={maxLength}/></label>
}
export function Select({label,name,options,value,required=true,onChange}:{
  label:string;name:string;options:Option[];value?:string|number;required?:boolean;onChange?:(value:string)=>void
}){
  return <label className="field">{label}<select name={name} defaultValue={value} required={required} onChange={event=>onChange?.(event.target.value)}>
    {options.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}
  </select></label>
}
export function Notes({label='Notes',value}:{label?:string;value?:string}){
  return <label className="field">{label}<textarea name="notes" defaultValue={value} rows={3}/></label>
}
export const options=(values:string[]):Option[]=>values.map(value=>({value,label:value.replaceAll('_',' ').toLowerCase().replace(/^./,c=>c.toUpperCase())}))
export function Empty({children}:{children:ReactNode}){
  return <div className="empty"><Inbox size={20}/><p>{children}</p></div>
}
export function Dialog({title,children,close}:{title:string;children:ReactNode;close:()=>void}){
  const dialog=useRef<HTMLDialogElement>(null)
  useEffect(()=>{dialog.current?.showModal()},[])
  return <dialog ref={dialog} onCancel={event=>{event.preventDefault();close()}} aria-labelledby="dialog-title">
    <div className="dialog-head"><h2 id="dialog-title">{title}</h2><button className="icon" aria-label="Close dialog" onClick={close}><X size={20}/></button></div>
    {children}
  </dialog>
}
export function Action({children,onClick}:{children:ReactNode;onClick:()=>void}){
  return <button className="primary" onClick={onClick}>{children}<ArrowUpRight size={17}/></button>
}
export function Panel({title,children,action}:{title:string;children:ReactNode;action?:ReactNode}){
  return <section className="panel"><div className="section-head"><h2>{title}</h2>{action}</div>{children}</section>
}
export function Pill({children,tone='neutral'}:{children:ReactNode;tone?:string}){
  return <span className={'pill '+tone}>{children}</span>
}
export function FormError({message}:{message:string}){
  return message?<p className="form-error" role="alert">{message}</p>:null
}
export const formData=(form:HTMLFormElement)=>new FormData(form)
export const value=(data:FormData,name:string)=>String(data.get(name)??'')
export const number=(data:FormData,name:string)=>Number(value(data,name))

