/**
 * Scryfall API 服务模块
 * 用于前端实时获取卡牌详细信息（图片、神谕文本、印刷版本等）
 *
 * 使用 localStorage 缓存，7 天过期，减少 API 请求。
 */
const ScryfallService = {
  CACHE_PREFIX: 'scryfall_',
  CACHE_TTL: 7 * 24 * 60 * 60 * 1000, // 7天缓存

  /**
   * 通过卡名获取卡牌完整信息
   * @param {string} cardName - 卡牌英文名
   * @returns {Promise<Object>} Scryfall card object
   */
  async fetchCard(cardName) {
    // 1. 检查 localStorage 缓存
    const cached = this._getCache(cardName);
    if (cached) return cached;

    // 2. 请求 Scryfall API
    const url = 'https://api.scryfall.com/cards/named?fuzzy=' + encodeURIComponent(cardName);
    const resp = await fetch(url);
    if (!resp.ok) {
      throw new Error('Scryfall API error: ' + resp.status);
    }
    const data = await resp.json();

    // 3. 缓存
    this._setCache(cardName, data);
    return data;
  },

  /**
   * 获取所有印刷版本
   * @param {string} printsSearchUri - Scryfall 返回的 prints_search_uri
   * @returns {Promise<Array>}
   */
  async fetchAllPrints(printsSearchUri) {
    const cacheKey = 'prints_' + encodeURIComponent(printsSearchUri);
    const cached = this._getCache(cacheKey);
    if (cached) return cached;

    const resp = await fetch(printsSearchUri);
    if (!resp.ok) return [];
    const data = await resp.json();
    const prints = (data.data || []).map(function(card) {
      return {
        set: card.set,
        set_name: card.set_name,
        collector_number: card.collector_number,
        rarity: card.rarity,
        image_uri: this._getImageUri(card),
        released_at: card.released_at || '',
      };
    }.bind(this));

    this._setCache(cacheKey, prints);
    return prints;
  },

  /**
   * 获取卡牌图片 URL（处理双面牌）
   */
  _getImageUri(card) {
    if (card.image_uris && card.image_uris.normal) {
      return card.image_uris.normal;
    }
    if (card.card_faces && card.card_faces[0] && card.card_faces[0].image_uris) {
      return card.card_faces[0].image_uris.normal;
    }
    return null;
  },

  /**
   * 渲染法术力符号为 HTML
   * @param {string} manaCost - 如 "{2}{W}{U}"
   * @returns {string} HTML 字符串
   */
  renderManaCost(manaCost) {
    if (!manaCost) return '';
    return manaCost.replace(/\{([^}]+)\}/g, function(match, symbol) {
      var encoded = symbol.replace(/\//g, '');
      return '<img src="https://svgs.scryfall.io/card-symbols/' + encoded + '.svg" ' +
             'alt="' + match + '" class="mana-symbol">';
    });
  },

  // ---- 缓存 ----

  _getCache(key) {
    try {
      var raw = localStorage.getItem(this.CACHE_PREFIX + key);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (Date.now() - parsed.timestamp > this.CACHE_TTL) {
        localStorage.removeItem(this.CACHE_PREFIX + key);
        return null;
      }
      return parsed.data;
    } catch (e) {
      return null;
    }
  },

  _setCache(key, data) {
    try {
      localStorage.setItem(this.CACHE_PREFIX + key, JSON.stringify({
        data: data,
        timestamp: Date.now(),
      }));
    } catch (e) {
      // localStorage 满了，清理旧缓存
      this._cleanOldCache();
    }
  },

  _cleanOldCache() {
    var now = Date.now();
    var keysToRemove = [];
    for (var i = 0; i < localStorage.length; i++) {
      var key = localStorage.key(i);
      if (key && key.indexOf(this.CACHE_PREFIX) === 0) {
        try {
          var parsed = JSON.parse(localStorage.getItem(key));
          if (now - parsed.timestamp > this.CACHE_TTL) {
            keysToRemove.push(key);
          }
        } catch (e) {
          keysToRemove.push(key);
        }
      }
    }
    for (var j = 0; j < keysToRemove.length; j++) {
      localStorage.removeItem(keysToRemove[j]);
    }
  },
};