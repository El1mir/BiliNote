import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/ember/lib/cn'

const BASE =
  'w-full rounded-control border border-line bg-surface px-3 py-2.5 text-body text-ink ' +
  'placeholder:text-ink-mute transition-[border-color,box-shadow] duration-150 ' +
  'focus:border-ember focus:outline-none focus:ring-[3px] focus:ring-ember-ring ' +
  'disabled:cursor-not-allowed disabled:opacity-60'

/** Ember Studio input — surface fill, 8px radius, 12px padding, terracotta focus ring. */
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return <input ref={ref} className={cn(BASE, 'h-10 py-0', className)} {...rest} />
  },
)

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={cn(BASE, 'resize-y leading-relaxed', className)} {...rest} />
  },
)
