declare module 'react' {
  export type CSSProperties = Record<string, any>;
  export type MouseEvent<T = any> = any;
  export type FC<P = any> = (props: P) => any;

  export function useEffect(effect: any, deps?: any[]): any;
  export function useMemo(factory: any, deps?: any[]): any;
  export function useRef<T = any>(initialValue?: T): any;
  export function useState<S = any>(initialState?: S | (() => S)): any;

  const React: any;
  export default React;
}

declare module 'react/jsx-runtime' {
  export const Fragment: any;
  export function jsx(type: any, props: any, key?: any): any;
  export function jsxs(type: any, props: any, key?: any): any;
  export function jsxDEV(type: any, props: any, key?: any): any;
}

// Minimal JSX namespace so TS doesn't complain about intrinsic elements.
declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any;
  }
}

