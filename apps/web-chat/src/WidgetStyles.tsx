import baseCss from "./widget.css?raw";

/** Both sheets belong to the chat document, never the embedding page. */
export function WidgetStyles({ customCss }: { customCss: string }) {
  return <><style data-cb-styles="base">{baseCss}</style><style data-cb-styles="custom">{customCss}</style></>;
}
