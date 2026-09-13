import { useLayoutEffect, useState, type RefObject } from "react";

export type ResponsiveSpace = {
  containerWidth: number;
  containerHeight: number;
  viewportWidth: number;
  viewportHeight: number;
};

const EMPTY_SPACE: ResponsiveSpace = {
  containerWidth: 0,
  containerHeight: 0,
  viewportWidth: 0,
  viewportHeight: 0,
};

/** Observe a container's width and the visible viewport height for responsive geometry. */
export function useResponsiveSpace<T extends HTMLElement>(
  elementRef: RefObject<T | null>,
): ResponsiveSpace {
  const [space, setSpace] = useState<ResponsiveSpace>(EMPTY_SPACE);

  useLayoutEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    const measure = () => {
      const next = {
        containerWidth: Math.round(element.clientWidth),
        containerHeight: Math.round(element.clientHeight),
        // CSS media queries use the layout viewport, including during pinch zoom.
        viewportWidth: Math.round(window.innerWidth),
        viewportHeight: Math.round(
          window.visualViewport?.height ?? window.innerHeight,
        ),
      };
      setSpace((current) =>
        current.containerWidth === next.containerWidth &&
        current.containerHeight === next.containerHeight &&
        current.viewportWidth === next.viewportWidth &&
        current.viewportHeight === next.viewportHeight
          ? current
          : next,
      );
    };

    measure();
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    window.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("resize", measure);

    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
      window.visualViewport?.removeEventListener("resize", measure);
    };
  }, [elementRef]);

  return space;
}

/** Track the visible viewport so fixed screens stay above mobile browser chrome. */
export function useVisibleViewportHeight(): number {
  const [height, setHeight] = useState(0);

  useLayoutEffect(() => {
    const measure = () => {
      const next = Math.round(
        window.visualViewport?.height ?? window.innerHeight,
      );
      setHeight((current) => (current === next ? current : next));
    };

    measure();
    window.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("resize", measure);
      window.visualViewport?.removeEventListener("resize", measure);
    };
  }, []);

  return height;
}
