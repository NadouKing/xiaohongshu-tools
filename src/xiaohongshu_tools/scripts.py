"""Read-only page probes; expressions run in Chrome's existing application context."""

UNWRAP = "const unwrap = x => x?.value ?? x?._value ?? x;"

PAGE_STATUS = r"""(() => {
  const visible = el => !!el && el.getBoundingClientRect().width > 0 &&
    el.getBoundingClientRect().height > 0;
  const text = document.body?.innerText || '';
  const u = window.__INITIAL_STATE__?.user;
  const info = u?.userInfo?.value ?? u?.userInfo?._value ?? u?.userInfo;
  return {
    ready: document.readyState !== 'loading',
    loggedIn: !!document.querySelector('.main-container .user .link-wrapper .channel') ||
      !!(info && info.guest === false && (info.userId || info.user_id)),
    loginRequired: visible(document.querySelector('.login-container')),
    verificationRequired: [...document.querySelectorAll('[class*=captcha], [id*=captcha]')]
      .some(visible) || /安全验证|请完成验证|访问频繁/.test(text.slice(0, 2000)),
    searchEmpty: [...document.querySelectorAll(
      '.search-layout .no-result, .search-layout .empty, .search-result-empty')]
      .some(el => visible(el) && /没有找到|暂无搜索结果|没有相关|未找到/.test(el.innerText)),
    searchLoading: [...document.querySelectorAll(
      '.search-layout .loading,.search-layout .skeleton')]
      .some(visible),
    inaccessible: [...document.querySelectorAll(
      '.access-wrapper,.error-wrapper,.not-found-wrapper')]
      .some(el => visible(el) && /无法浏览|已被删除|不存在|私密|仅作者/.test(el.innerText))
  };
})()"""

SEARCH_DATA = r"""(() => {
  const f = window.__INITIAL_STATE__?.search?.feeds;
  const items = f?.value ?? f?._value ?? f;
  return Array.isArray(items) ? JSON.parse(JSON.stringify(items)) : null;
})()"""


def note_data(item_id: str) -> str:
    import json

    return """(() => {
      const m = window.__INITIAL_STATE__?.note?.noteDetailMap;
      const root = m?.value ?? m?._value ?? m;
      const item = root?.[ID];
      if (!item?.note?.noteId) return null;
      return JSON.parse(JSON.stringify(item));
    })()""".replace("ID", json.dumps(item_id))


COMMENT_DOM = r"""(() => {
  const text = el => el?.innerText?.trim() || '';
  const items = [...document.querySelectorAll('.parent-comment')].map(el => ({
    id: el.id || el.getAttribute('data-id') || '',
    content: text(el.querySelector('.content .note-text, .content .content, .content')),
    userInfo: {nickname: text(el.querySelector('.author .name, .author-wrapper .name'))},
    publishedLabel: text(el.querySelector('.date, .time'))
  })).filter(x => x.content);
  return {
    items,
    ended: /THE\s*END/i.test(text(document.querySelector('.end-container'))) ||
      /这是一片荒地|暂无评论/.test(text(document.querySelector('.no-comments-text')))
  };
})()"""

SCROLL_COMMENTS = r"""(() => {
  document.querySelector('.comments-container')?.scrollIntoView({block:'nearest'});
  for (const sel of ['.note-scroller', '.comments-container']) {
    const el = document.querySelector(sel);
    if (el && el.scrollHeight > el.clientHeight) {
      el.scrollBy({top: Math.max(550, el.clientHeight * .8), behavior:'instant'});
      return true;
    }
  }
  window.scrollBy(0, 650);
  return true;
})()"""


def select_sort(sort: str) -> str:
    import json

    return """(() => {
      const visible = el => el && el.getBoundingClientRect().height > 0;
      const panel = document.querySelector('.filter-panel');
      if (!panel) return false;
      for (const group of panel.querySelectorAll('.filters')) {
        if (group.querySelector(':scope > span')?.textContent.trim() !== '排序依据') continue;
        for (const el of group.querySelectorAll('.tags')) {
          if (el.textContent.trim() === SORT && visible(el)) { el.click(); return true; }
        }
      }
      return false;
    })()""".replace("SORT", json.dumps(sort, ensure_ascii=False))


FILTER_COORDINATES = r"""(() => {
  const r = document.querySelector('div.filter')?.getBoundingClientRect();
  return r ? {x:r.x+r.width/2, y:r.y+r.height/2} : null;
})()"""
