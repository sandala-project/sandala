import { useEffect, useLayoutEffect, useState, type RefObject } from "react";

export type PopoverPosition = {
  left: number;
  maxHeight: number;
  placement: "bottom" | "top";
  top: number;
  width: number;
};

type UsePopoverArgs = {
  align?: "end" | "start";
  anchorRef: RefObject<HTMLElement | null>;
  contentRef: RefObject<HTMLElement | null>;
  deps?: unknown[];
  isOpen: boolean;
  matchWidth?: boolean;
  minWidth?: number;
  onClose: () => void;
};

export function usePopover({
  align = "start",
  anchorRef,
  contentRef,
  deps = [],
  isOpen,
  matchWidth = true,
  minWidth = 0,
  onClose,
}: UsePopoverArgs) {
  const [position, setPosition] = useState<PopoverPosition | null>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (anchorRef.current?.contains(target) !== true && contentRef.current?.contains(target) !== true) {
        onClose();
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [anchorRef, contentRef, isOpen, onClose]);

  useLayoutEffect(() => {
    if (!isOpen) {
      setPosition(null);
      return;
    }

    function updatePosition() {
      const anchor = anchorRef.current;
      if (!anchor) {
        return;
      }

      const rect = anchor.getBoundingClientRect();
      const viewportPadding = 16;
      const gap = 6;
      const desiredHeight = 220;
      const availableBelow = window.innerHeight - rect.bottom - viewportPadding - gap;
      const availableAbove = rect.top - viewportPadding - gap;
      const placeAbove = availableBelow < 160 && availableAbove > availableBelow;
      const maxHeight = Math.max(120, Math.min(desiredHeight, placeAbove ? availableAbove : availableBelow));
      const width = Math.max(matchWidth ? rect.width : 0, minWidth);
      const unclampedLeft = align === "end" ? rect.right - width : rect.left;
      const left = Math.max(viewportPadding, Math.min(unclampedLeft, window.innerWidth - viewportPadding - width));

      setPosition({
        left,
        maxHeight,
        placement: placeAbove ? "top" : "bottom",
        top: placeAbove ? rect.top - gap : rect.bottom + gap,
        width,
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [anchorRef, isOpen, ...deps]);

  return position;
}
