(() => {
  const state = window.__PRELOADED_STATE__ || window['__PRELOADED_STATE__'];
  if (!state || !Array.isArray(state.itemList)) {
    console.error("[LOWES_STATE] __PRELOADED_STATE__.itemList not found");
    return;
  }

  const keep = {
    itemCount: state.itemCount,
    productCount: state.productCount,
    adjustedNextOffset: state.adjustedNextOffset,
    pagination: state.pagination,
    searchTerm: state.searchTerm,
    offset: state.offset,
    pageSize: state.pageSize,
    selectedStore: state.selectedStore,
    nearbyStores: state.nearbyStores,
    itemList: state.itemList,
  };
  const text = JSON.stringify(keep, null, 2);

  const done = () => {
    console.log(
      `[LOWES_STATE] copied itemList=${keep.itemList.length}, chars=${text.length}. ` +
        "Paste into lowes/references/lowes_ldy_main_state.json"
    );
  };

  if (typeof copy === "function") {
    copy(text);
    done();
    return;
  }

  navigator.clipboard.writeText(text).then(done).catch((error) => {
    console.error("[LOWES_STATE] clipboard copy failed", error);
    console.log(text);
  });
})();
