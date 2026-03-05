'use client'

import {
  createElement,
  forwardRef,
  type ComponentPropsWithoutRef,
  type ForwardRefExoticComponent,
  type PropsWithoutRef,
  type RefAttributes,
} from 'react'

type MotionExtraProps = {
  animate?: unknown
  initial?: unknown
  whileHover?: unknown
  whileTap?: unknown
  variants?: unknown
  transition?: unknown
}

type MotionComponent<TTag extends keyof JSX.IntrinsicElements> = ForwardRefExoticComponent<
  PropsWithoutRef<ComponentPropsWithoutRef<TTag> & MotionExtraProps> & RefAttributes<Element>
>

const passthroughMotion = <TTag extends keyof JSX.IntrinsicElements>(tag: TTag): MotionComponent<TTag> => {
  const Component = forwardRef<Element, ComponentPropsWithoutRef<TTag> & MotionExtraProps>(function MotionPrimitive(
    {
      animate: _animate,
      initial: _initial,
      whileHover: _whileHover,
      whileTap: _whileTap,
      variants: _variants,
      transition: _transition,
      ...rest
    },
    ref
  ) {
    return createElement(tag, { ...rest, ref })
  })

  return Component as MotionComponent<TTag>
}

type MotionNamespace = { [K in keyof JSX.IntrinsicElements]: MotionComponent<K> }

const componentCache = new Map<keyof JSX.IntrinsicElements, MotionComponent<keyof JSX.IntrinsicElements>>()

export const motion: MotionNamespace = new Proxy({} as MotionNamespace, {
  get: (_target, tag) => {
    if (typeof tag !== 'string') {
      return undefined
    }

    const elementTag = tag as keyof JSX.IntrinsicElements
    const cached = componentCache.get(elementTag)
    if (cached) {
      return cached
    }

    const component = passthroughMotion(elementTag) as MotionComponent<keyof JSX.IntrinsicElements>
    component.displayName = `Motion(${elementTag})`
    componentCache.set(elementTag, component)
    return component
  },
})

export const useInView = (_ref: unknown, _options?: unknown): boolean => true
