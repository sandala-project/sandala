import { useEffect, useMemo, useState } from "react";

type VirtualRow = {
  index: number;
  start: number;
};

export function useVirtualizedNodeTable(args: {
  count: number;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onEndReached: () => void;
  overscan?: number;
  rowHeight: number;
  scrollElement: HTMLElement | null;
}) {
  const {
    count,
    hasNextPage,
    isFetchingNextPage,
    onEndReached,
    overscan = 6,
    rowHeight,
    scrollElement,
  } = args;
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  useEffect(() => {
    if (scrollElement === null) {
      return;
    }

    const updateMetrics = () => {
      setScrollTop(scrollElement.scrollTop);
      setViewportHeight(Math.max(0, scrollElement.clientHeight));
    };

    updateMetrics();

    const handleScroll = () => {
      setScrollTop(scrollElement.scrollTop);
    };

    const resizeObserver = new ResizeObserver(() => {
      updateMetrics();
    });

    resizeObserver.observe(scrollElement);
    scrollElement.addEventListener("scroll", handleScroll, { passive: true });

    return () => {
      resizeObserver.disconnect();
      scrollElement.removeEventListener("scroll", handleScroll);
    };
  }, [scrollElement]);

  const bodyHeight = count * rowHeight;

  const visibleRange = useMemo(() => {
    if (count === 0) {
      return { endIndex: -1, startIndex: 0 };
    }

    if (viewportHeight <= 0) {
      return {
        endIndex: Math.min(count - 1, overscan * 2),
        startIndex: 0,
      };
    }

    const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    const endIndex = Math.min(
      count - 1,
      Math.ceil((scrollTop + viewportHeight) / rowHeight) + overscan,
    );

    return { endIndex, startIndex };
  }, [count, overscan, rowHeight, scrollTop, viewportHeight]);

  const virtualRows = useMemo<VirtualRow[]>(() => {
    if (visibleRange.endIndex < visibleRange.startIndex) {
      return [];
    }

    const next: VirtualRow[] = [];
    for (let index = visibleRange.startIndex; index <= visibleRange.endIndex; index += 1) {
      next.push({
        index,
        start: index * rowHeight,
      });
    }

    return next;
  }, [rowHeight, visibleRange.endIndex, visibleRange.startIndex]);

  useEffect(() => {
    if (!hasNextPage || isFetchingNextPage || viewportHeight <= 0) {
      return;
    }

    const remaining = bodyHeight - (scrollTop + viewportHeight);
    if (remaining < Math.max(rowHeight * 6, 400)) {
      onEndReached();
    }
  }, [bodyHeight, hasNextPage, isFetchingNextPage, onEndReached, rowHeight, scrollTop, viewportHeight]);

  return {
    bodyHeight,
    virtualRows,
  };
}
