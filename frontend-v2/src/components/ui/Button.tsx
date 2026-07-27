import { forwardRef, type ButtonHTMLAttributes, type PropsWithChildren } from 'react'

type ButtonProps = PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' }>

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', className = '', ...props },
  ref,
) {
  return <button ref={ref} className={`button button-${variant} ${className}`} {...props} />
})
