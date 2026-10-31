/**
 * React 19 removed the global `JSX` namespace; it now lives at `React.JSX`.
 *
 * react-markdown 8.0.7 still ships a `.ts` source file (lib/complex-types.ts) that
 * writes `keyof JSX.IntrinsicElements` unqualified, so under React 19 types the
 * namespace is missing, `NormalComponents` collapses, and every custom renderer
 * fails with TS2322 against `Components`. Because that file is a `.ts` rather than a
 * `.d.ts`, `skipLibCheck` does not exempt it and the failure is unavoidable from
 * our side of the dependency.
 *
 * Re-publishing the namespace globally is the documented React 19 interop shim for
 * libraries that have not migrated yet. It only forwards to `React.JSX`, so element
 * typing for our own components is unchanged.
 */
import type * as React from 'react'

declare global {
  namespace JSX {
    type ElementType = React.JSX.ElementType
    interface Element extends React.JSX.Element {}
    interface ElementClass extends React.JSX.ElementClass {}
    interface ElementAttributesProperty extends React.JSX.ElementAttributesProperty {}
    interface ElementChildrenAttribute extends React.JSX.ElementChildrenAttribute {}
    type LibraryManagedAttributes<C, P> = React.JSX.LibraryManagedAttributes<C, P>
    interface IntrinsicAttributes extends React.JSX.IntrinsicAttributes {}
    interface IntrinsicClassAttributes<T> extends React.JSX.IntrinsicClassAttributes<T> {}
    interface IntrinsicElements extends React.JSX.IntrinsicElements {}
  }
}
