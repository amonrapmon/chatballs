import type { PagedPayload } from "./usePagedResource";

// Весь набор постранично. Нужен там, где интерфейс работает не со страницей, а
// с полным списком: выбор знаний агента, выгрузка. Обычные списки так грузить
// нельзя — это ровно то, от чего уходили, когда вводили страницы.

export async function allPages<T>(load: (page: number) => Promise<PagedPayload<T>>): Promise<T[]> {
  const items: T[] = [];
  let page = 1;
  for (;;) {
    const payload = await load(page);
    items.push(...payload.items);
    if (payload.items.length === 0 || payload.page >= payload.pageCount) return items;
    page = payload.page + 1;
  }
}
