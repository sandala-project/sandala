import { useEffect, useRef, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import { createPortal } from "react-dom";
import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import StarterKit from "@tiptap/starter-kit";
import { TextAreaField } from "./Field";
import { Icon, type IconName } from "./Icon";
import { usePopover } from "./usePopover";
import type { TranslationKey } from "../locales";

type RichTextBlockFormat = "paragraph" | "heading-1" | "heading-2" | "heading-3" | "heading-4";
type RichTextAlignment = "left" | "center" | "right" | "justify";

const headingLevels: Record<Exclude<RichTextBlockFormat, "paragraph">, 1 | 2 | 3 | 4> = {
  "heading-1": 1,
  "heading-2": 2,
  "heading-3": 3,
  "heading-4": 4,
};

type RichTextFieldProps = {
  canWrite: boolean;
  error?: string;
  hideLabel?: boolean;
  label: string;
  onImageUpload?: (file: File) => Promise<{ url: string }>;
  onBlur: () => void;
  onChange: (value: string) => void;
  t: (key: TranslationKey) => string;
  value: unknown;
};

export function RichTextField({
  canWrite,
  error,
  hideLabel = false,
  label,
  onBlur,
  onChange,
  onImageUpload,
  t,
  value,
}: RichTextFieldProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isSourceMode, setIsSourceMode] = useState(false);
  const [sourceValue, setSourceValue] = useState(() => asHtml(value));
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const editor = useEditor({
    content: asHtml(value),
    editable: canWrite,
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3, 4] },
      }),
      Underline,
      Image.configure({
        inline: true,
        // The image asset remains untouched: Tiptap persists only these
        // presentation dimensions in the RichText HTML.
        resize: canWrite
          ? {
              enabled: true,
              directions: ["top-left", "top-right", "bottom-left", "bottom-right"],
              minWidth: 50,
              minHeight: 50,
              alwaysPreserveAspectRatio: true,
            }
          : false,
      }),
      Link.configure({
        autolink: true,
        defaultProtocol: "https",
        openOnClick: false,
      }),
      TextAlign.configure({
        types: ["heading", "paragraph"],
      }),
    ],
    editorProps: {
      attributes: {
        class: "rich-text-content",
      },
    },
    onBlur,
    onUpdate: ({ editor: updatedEditor }) => onChange(updatedEditor.getHTML()),
  });

  useEffect(() => {
    if (editor === null || editor.isDestroyed || isSourceMode) {
      return;
    }

    const nextValue = asHtml(value);
    const currentValue = editor.getHTML();
    if (currentValue !== nextValue && !(nextValue.length === 0 && isEmptyDocument(currentValue))) {
      editor.commands.setContent(nextValue, { emitUpdate: false });
    }
  }, [editor, isSourceMode, value]);

  useEffect(() => {
    if (!isFullscreen) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsFullscreen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isFullscreen]);

  if (editor === null || editor.isDestroyed) {
    return null;
  }

  const toggleSourceMode = () => {
    if (!isSourceMode) {
      setSourceValue(editor.getHTML());
      setIsSourceMode(true);
      return;
    }

    editor.commands.setContent(sourceValue, { emitUpdate: false });
    onChange(editor.getHTML());
    setIsSourceMode(false);
  };

  const setLink = () => {
    const currentUrl = editor.getAttributes("link").href as string | undefined;
    const url = window.prompt(t("pages.nodes.editor.richText.linkPrompt"), currentUrl ?? "");
    if (url === null) {
      return;
    }
    if (url.trim().length === 0) {
      editor.chain().focus().unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: url.trim() }).run();
  };

  const uploadImage = async (file: File) => {
    if (onImageUpload === undefined) return;
    setIsUploadingImage(true);
    try {
      const image = await onImageUpload(file);
      editor.chain().focus().setImage({ src: image.url }).run();
      setUploadError(null);
    } catch (error) {
      setUploadError(t("pages.nodes.editor.richText.imageUploadFailed"));
    } finally {
      setIsUploadingImage(false);
    }
  };

  const editorSurface = (
    <div className="rich-text-editor">
      {!hideLabel ? <div className="field-label">{label}</div> : null}
      <div className="rich-text-shell">
        <div aria-label={t("pages.nodes.editor.richText.toolbar")} className="rich-text-toolbar" role="toolbar">
          <ToolbarButton
            active={editor.isActive("bold")}
            disabled={!canWrite || isSourceMode}
            icon="bold"
            label={t("pages.nodes.editor.richText.bold")}
            onClick={() => editor.chain().focus().toggleBold().run()}
          />
          <ToolbarButton
            active={editor.isActive("italic")}
            disabled={!canWrite || isSourceMode}
            icon="italic"
            label={t("pages.nodes.editor.richText.italic")}
            onClick={() => editor.chain().focus().toggleItalic().run()}
          />
          <ToolbarButton
            active={editor.isActive("underline")}
            disabled={!canWrite || isSourceMode}
            icon="underline"
            label={t("pages.nodes.editor.richText.underline")}
            onClick={() => editor.chain().focus().toggleUnderline().run()}
          />
          <ToolbarFormatSelect
            disabled={!canWrite || isSourceMode}
            label={t("pages.nodes.editor.richText.heading")}
            onChange={(format) => {
              const chain = editor.chain().focus();
              if (format === "paragraph") {
                chain.setParagraph().run();
                return;
              }
              chain.setHeading({ level: headingLevels[format] }).run();
            }}
            options={[
              { label: t("pages.nodes.editor.richText.paragraph"), value: "paragraph" },
              { label: t("pages.nodes.editor.richText.heading1"), value: "heading-1" },
              { label: t("pages.nodes.editor.richText.heading2"), value: "heading-2" },
              { label: t("pages.nodes.editor.richText.heading3"), value: "heading-3" },
              { label: t("pages.nodes.editor.richText.heading4"), value: "heading-4" },
            ]}
            value={getBlockFormat(editor)}
          />
          <ToolbarAlignmentSelect
            disabled={!canWrite || isSourceMode}
            editor={editor}
            labels={{
              center: t("pages.nodes.editor.richText.alignCenter"),
              justify: t("pages.nodes.editor.richText.alignJustify"),
              left: t("pages.nodes.editor.richText.alignLeft"),
              right: t("pages.nodes.editor.richText.alignRight"),
            }}
            value={getTextAlignment(editor)}
          />
          <ToolbarButton
            active={editor.isActive("bulletList")}
            disabled={!canWrite || isSourceMode}
            icon="list"
            label={t("pages.nodes.editor.richText.bulletList")}
            onClick={() => editor.chain().focus().toggleBulletList().run()}
          />
          <ToolbarButton
            active={editor.isActive("orderedList")}
            disabled={!canWrite || isSourceMode}
            icon="list-ordered"
            label={t("pages.nodes.editor.richText.orderedList")}
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
          />
          <ToolbarButton
            active={editor.isActive("link")}
            disabled={!canWrite || isSourceMode}
            icon="link"
            label={t("pages.nodes.editor.richText.link")}
            onClick={setLink}
          />
          {onImageUpload !== undefined ? (
            <>
              <input
                accept="image/jpeg,image/png,image/gif,image/webp"
                className="visually-hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file !== undefined) void uploadImage(file);
                }}
                ref={imageInputRef}
                type="file"
              />
              <ToolbarButton
                disabled={!canWrite || isSourceMode || isUploadingImage}
                icon="image-upload"
                label={t("pages.nodes.editor.richText.image")}
                onClick={() => imageInputRef.current?.click()}
              />
            </>
          ) : null}
          <span className="rich-text-toolbar-spacer" />
          <ToolbarButton
            active={isSourceMode}
            disabled={!canWrite}
            icon="code"
            label={t("pages.nodes.editor.richText.source")}
            onClick={toggleSourceMode}
          />
          <ToolbarButton
            disabled={false}
            icon={isFullscreen ? "minimize" : "maximize"}
            label={isFullscreen ? t("pages.nodes.editor.richText.exitFullscreen") : t("pages.nodes.editor.richText.fullscreen")}
            onClick={() => setIsFullscreen((current) => !current)}
          />
        </div>
        {isSourceMode ? (
          <TextAreaField
            label=""
            onBlur={onBlur}
            onChange={(event) => {
              setSourceValue(event.target.value);
              onChange(event.target.value);
            }}
            readOnly={!canWrite}
            rows={14}
            value={sourceValue}
          />
        ) : (
          <EditorContent editor={editor} />
        )}
      </div>
      {error ? <span className="field-error">{error}</span> : null}
      {uploadError ? <span className="field-error">{uploadError}</span> : null}
    </div>
  );

  return <div className={isFullscreen ? "rich-text-fullscreen" : ""}>{editorSurface}</div>;
}

function ToolbarButton({
  active = false,
  disabled,
  icon,
  label,
  onClick,
}: {
  active?: boolean;
  disabled: boolean;
  icon: IconName;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      className={`rich-text-toolbar-button ${active ? "is-active" : ""}`.trim()}
      disabled={disabled}
      onClick={onClick}
      title={label}
      type="button"
    >
      <Icon name={icon} size="small" weight="strong" />
    </button>
  );
}

function ToolbarFormatSelect({
  disabled,
  label,
  onChange,
  options,
  value,
}: {
  disabled: boolean;
  label: string;
  onChange: (value: RichTextBlockFormat) => void;
  options: Array<{ label: string; value: RichTextBlockFormat }>;
  value: RichTextBlockFormat;
}) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const selectedOption = options.find((option) => option.value === value) ?? options[0];
  const menuPosition = usePopover({
    anchorRef: triggerRef,
    contentRef: menuRef,
    isOpen,
    matchWidth: false,
    minWidth: 150,
    onClose: () => setIsOpen(false),
  });

  return (
    <>
      <button
        aria-expanded={isOpen}
        aria-label={label}
        className="rich-text-toolbar-format-trigger"
        disabled={disabled}
        onClick={() => setIsOpen((current) => !current)}
        ref={triggerRef}
        title={label}
        type="button"
      >
        <span>{selectedOption?.label}</span>
        <Icon name="chevron-down" size="tiny" weight="strong" />
      </button>
      {isOpen && !disabled && menuPosition
        ? createPortal(
            <div
              className={`select-menu rich-text-toolbar-format-menu select-menu-${menuPosition.placement}`}
              ref={menuRef}
              style={{
                left: `${menuPosition.left}px`,
                maxHeight: `${menuPosition.maxHeight}px`,
                top: `${menuPosition.top}px`,
                width: `${menuPosition.width}px`,
              }}
            >
              {options.map((option) => (
                <button
                  className={`select-option ${option.value === value ? "is-selected" : ""}`.trim()}
                  key={option.value}
                  onClick={(event) => {
                    event.preventDefault();
                    onChange(option.value);
                    setIsOpen(false);
                    triggerRef.current?.focus();
                  }}
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

function ToolbarAlignmentSelect({
  disabled,
  editor,
  labels,
  value,
}: {
  disabled: boolean;
  editor: NonNullable<ReturnType<typeof useEditor>>;
  labels: Record<RichTextAlignment, string>;
  value: RichTextAlignment;
}) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const options: Array<{ icon: IconName; value: RichTextAlignment }> = [
    { icon: "align-left", value: "left" },
    { icon: "align-center", value: "center" },
    { icon: "align-right", value: "right" },
    { icon: "align-justify", value: "justify" },
  ];
  const currentOption = options.find((option) => option.value === value) ?? options[0]!;
  const menuPosition = usePopover({
    anchorRef: triggerRef,
    contentRef: menuRef,
    isOpen,
    matchWidth: false,
    minWidth: 100,
    onClose: () => setIsOpen(false),
  });

  return (
    <>
      <button
        aria-expanded={isOpen}
        aria-label={labels[value]}
        className="rich-text-toolbar-button rich-text-toolbar-alignment-trigger"
        disabled={disabled}
        onClick={() => setIsOpen((current) => !current)}
        ref={triggerRef}
        title={labels[value]}
        type="button"
      >
        <Icon name={currentOption.icon} size="small" weight="strong" />
      </button>
      {isOpen && !disabled && menuPosition
        ? createPortal(
            <div
              aria-label={labels[value]}
              className={`select-menu rich-text-toolbar-alignment-menu select-menu-${menuPosition.placement}`}
              ref={menuRef}
              role="menu"
              style={{
                left: `${menuPosition.left}px`,
                maxHeight: `${menuPosition.maxHeight}px`,
                top: `${menuPosition.top}px`,
                width: `${menuPosition.width}px`,
              }}
            >
              {options
                .filter((option) => option.value !== value)
                .map((option) => (
                  <button
                    aria-label={labels[option.value]}
                    className="rich-text-toolbar-alignment-option"
                    key={option.value}
                    onClick={(event) => {
                      event.preventDefault();
                      editor.chain().focus().setTextAlign(option.value).run();
                      setIsOpen(false);
                      triggerRef.current?.focus();
                    }}
                    title={labels[option.value]}
                    type="button"
                  >
                    <Icon name={option.icon} size="small" weight="strong" />
                  </button>
                ))}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

function getBlockFormat(editor: NonNullable<ReturnType<typeof useEditor>>): RichTextBlockFormat {
  for (const level of [1, 2, 3, 4] as const) {
    if (editor.isActive("heading", { level })) {
      return `heading-${level}`;
    }
  }
  return "paragraph";
}

function getTextAlignment(editor: NonNullable<ReturnType<typeof useEditor>>): RichTextAlignment {
  if (editor.isActive({ textAlign: "center" })) {
    return "center";
  }
  if (editor.isActive({ textAlign: "right" })) {
    return "right";
  }
  if (editor.isActive({ textAlign: "justify" })) {
    return "justify";
  }
  return "left";
}

function asHtml(value: unknown) {
  return typeof value === "string" ? value : "";
}

function isEmptyDocument(value: string) {
  return value === "<p></p>";
}
