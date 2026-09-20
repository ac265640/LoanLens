import type { CSSProperties } from 'react';

interface FoldTextProps {
  text: string;
  splitBy?: 'char' | 'word';
  hinge?: 'top' | 'bottom';
  trigger?: 'mount' | 'scroll';
  delay?: number;
  duration?: number;
  stagger?: number;
  ease?: string;
  perspective?: number;
  creaseShading?: number;
  fontSize?: string | number;
  fontWeight?: string | number;
  color?: string;
  style?: CSSProperties;
}

declare function FoldText(props: FoldTextProps): JSX.Element;
export default FoldText;
