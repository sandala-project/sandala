import {
  AlignCenter,
  AlignJustify,
  AlignLeft,
  AlignRight,
  ArrowDown,
  ArrowDownUp,
  ArrowUp,
  Bold,
  CodeXml,
  Columns3,
  Copy,
  Funnel,
  GripVertical,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleQuestionMark,
  ImageUp,
  Italic,
  Link,
  List,
  ListOrdered,
  ListTree,
  ListFilter,
  Maximize2,
  Minimize2,
  Pencil,
  Plus,
  Rows2,
  Rows4,
  RefreshCw,
  Trash2,
  Underline,
  Table2,
  X,
  type LucideIcon,
  type LucideProps,
} from "lucide-react";

const icons = {
  "align-center": AlignCenter,
  "align-justify": AlignJustify,
  "align-left": AlignLeft,
  "align-right": AlignRight,
  "arrow-down": ArrowDown,
  "arrow-down-up": ArrowDownUp,
  "arrow-up": ArrowUp,
  bold: Bold,
  "chevron-down": ChevronDown,
  "chevron-left": ChevronLeft,
  "chevron-right": ChevronRight,
  "error-details": CircleQuestionMark,
  code: CodeXml,
  copy: Copy,
  filter: Funnel,
  "field-reorder": GripVertical,
  "image-upload": ImageUp,
  italic: Italic,
  link: Link,
  list: List,
  "list-ordered": ListOrdered,
  "nodes-table-view": Table2,
  "nodes-tree-view": ListTree,
  "nodes-density-comfortable": Rows4,
  "nodes-density-expanded": Rows2,
  "nodes-filter": ListFilter,
  "nodes-sort": ArrowDownUp,
  "nodes-columns": Columns3,
  "nodes-create": Plus,
  "nodes-reload": RefreshCw,
  maximize: Maximize2,
  minimize: Minimize2,
  pencil: Pencil,
  plus: Plus,
  trash: Trash2,
  underline: Underline,
  x: X,
} satisfies Record<string, LucideIcon>;

export type IconName = keyof typeof icons;
export type IconSize = "tiny" | "small" | "medium" | "large";
export type IconWeight = "regular" | "strong";

type IconProps = Omit<LucideProps, "ref" | "size" | "strokeWidth"> & {
  name: IconName;
  size?: IconSize;
  weight?: IconWeight;
};

const sizes: Record<IconSize, number> = {
  tiny: 12,
  small: 14,
  medium: 16,
  large: 20,
};

const strokeWidths: Record<IconWeight, number> = {
  regular: 1,
  strong: 2,
};

export function Icon({ name, size = "medium", weight = "regular", ...props }: IconProps) {
  const IconComponent = icons[name];
  return <IconComponent aria-hidden="true" size={sizes[size]} strokeWidth={strokeWidths[weight]} {...props} />;
}
