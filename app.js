/**
 * MTG Card Keeper - 前端查询引擎
 *
 * 纯前端实现，无需后端。加载 card_database.json 后在浏览器本地查询。
 * 移植自 Python card_keeper/database.py
 */

const CardKeeper = {
  // ============================================================
  // 常量（与 database.py 保持一致）
  // ============================================================

  EDH_TIERS: {
    core: { label: '⭐ 核心', color: '#ff6b6b' },
    common: { label: '✅ 常用', color: '#51cf66' },
    occasional: { label: '⚠️ 偶用', color: '#ffd43b' },
    rare: { label: '❌ 少用', color: '#868e96' },
    unknown: { label: '❓ 未收录', color: '#adb5bd' },
  },

  RECOMMENDATIONS: {
    keep_strong: { label: '🟢 强烈保留', color: '#2b8a3e' },
    keep: { label: '🟢 保留', color: '#40c057' },
    keep_constructed: { label: '🟡 构筑专用', color: '#fab005' },
    keep_edh: { label: '🟡 EDH专用', color: '#fab005' },
    maybe: { label: '🟠 可保留', color: '#fd7e14' },
    drop: { label: '🔴 可不保留', color: '#e03131' },
  },

  RARITY_CN: {
    mythic: '秘稀', rare: '稀有', uncommon: '非普通',
    common: '普通', special: '特殊', bonus: '额外', unknown: '未知',
  },

  COLOR_CN: {
    W: '白', U: '蓝', B: '黑', R: '红', G: '绿',
    Colorless: '无色', Multicolor: '多色',
  },

  // ============================================================
  // 数据
  // ============================================================

  cards: {},        // { cardName: cardData }
  nameIndex: {},    // { lowercase_name: original_name } 用于大小写不敏感搜索
  setsIndex: {},    // { set_code: set_name } 系列代码→名称映射
  setsToCards: {},  // { set_code: [cardName, ...] } 系列→卡牌反向索引
  _loaded: false,

  // ============================================================
  // 初始化
  // ============================================================

  /**
   * 加载数据库 JSON 和系列索引
   * @param {string} jsonPath - card_database.json 路径
   * @param {string} [setsIndexPath] - sets_index.json 路径（可选）
   */
  async init(jsonPath, setsIndexPath) {
    const resp = await fetch(jsonPath);
    if (!resp.ok) {
      throw new Error(`加载数据库失败: ${resp.status} ${resp.statusText}`);
    }
    this.cards = await resp.json();
    this.buildIndex();

    // 加载系列索引（如果提供）
    if (setsIndexPath) {
      try {
        const setsResp = await fetch(setsIndexPath);
        if (setsResp.ok) {
          this.setsIndex = await setsResp.json();
          this.buildSetsIndex();
        }
      } catch (e) {
        console.warn('系列索引加载失败，按系列浏览功能不可用', e);
      }
    }

    this._loaded = true;
  },

  buildIndex() {
    this.nameIndex = {};
    for (const name of Object.keys(this.cards)) {
      if (name.startsWith('__')) continue; // 跳过元数据键
      this.nameIndex[name.toLowerCase()] = name;
    }
  },

  /**
   * 构建系列→卡牌反向索引
   */
  buildSetsIndex() {
    this.setsToCards = {};
    for (const name of Object.keys(this.cards)) {
      if (name.startsWith('__')) continue;
      const sets = this.cards[name].sets || [];
      for (const code of sets) {
        if (!this.setsToCards[code]) this.setsToCards[code] = [];
        this.setsToCards[code].push(name);
      }
    }
  },

  /**
   * 获取所有系列（含卡牌数），按名称排序
   * @returns {Array<{code, name, count}>}
   */
  getAllSets() {
    return Object.keys(this.setsIndex)
      .map(code => ({
        code,
        name: this.setsIndex[code],
        count: (this.setsToCards[code] || []).length,
      }))
      .filter(s => s.count > 0)
      .sort((a, b) => a.name.localeCompare(b.name));
  },

  /**
   * 获取指定系列中的所有卡牌
   * @param {string} setCode - 系列代码
   * @returns {Array} 格式化后的卡牌列表
   */
  getCardsBySet(setCode) {
    const names = this.setsToCards[setCode] || [];
    return names
      .map(n => this.cards[n])
      .filter(Boolean)
      .map(c => this._formatCard(c));
  },

  /**
   * 获取所有 Combo 潜力卡（combo_legacy 标记）
   * @param {Object} [filter] - 筛选条件 {rarity, color, type}
   * @returns {Array} 格式化后的卡牌列表
   */
  getComboLegacyCards(filter) {
    const cards = [];
    for (const [name, card] of Object.entries(this.cards)) {
      if (name.startsWith('__')) continue;
      if (!card.combo_legacy) continue;
      if (filter) {
        if (filter.rarity && card.rarity !== filter.rarity) continue;
        if (filter.color && card.color_category !== filter.color) continue;
        if (filter.type && card.type_category !== filter.type) continue;
      }
      cards.push(this._formatCard(card));
    }
    cards.sort((a, b) => a.name.localeCompare(b.name));
    return cards;
  },

  /**
   * Combo 潜力卡统计
   */
  comboLegacyStats() {
    const stats = {
      total: 0,
      by_rarity: {},
      by_color: {},
      by_type: {},
      has_chinese: 0,
    };
    for (const [name, card] of Object.entries(this.cards)) {
      if (name.startsWith('__')) continue;
      if (!card.combo_legacy) continue;
      stats.total++;
      stats.by_rarity[card.rarity] = (stats.by_rarity[card.rarity] || 0) + 1;
      stats.by_color[card.color_category] = (stats.by_color[card.color_category] || 0) + 1;
      stats.by_type[card.type_category] = (stats.by_type[card.type_category] || 0) + 1;
      if (card.chinese_name) stats.has_chinese++;
    }
    return stats;
  },

  // ============================================================
  // 判断逻辑（移植自 database.py）
  // ============================================================

  /**
   * EDH 有用性等级判断
   * @returns {"core"|"common"|"occasional"|"rare"|"unknown"}
   */
  classifyEdh(numDecks, inclusion) {
    if (numDecks === 0 && inclusion === 0) return 'unknown';
    if (numDecks > 50000 || inclusion > 0.30) return 'core';
    if (numDecks > 5000 || inclusion > 0.05) return 'common';
    if (numDecks > 500 || inclusion > 0.01) return 'occasional';
    return 'rare';
  },

  /**
   * 保留建议判断
   * @returns {string} 建议key
   */
  recommend(constructedUsed, edhTier) {
    const edhGood = edhTier === 'core' || edhTier === 'common';
    const edhOk = edhTier === 'occasional';

    if (constructedUsed && edhGood) return 'keep_strong';
    if (constructedUsed && edhOk) return 'keep';
    if (constructedUsed) return 'keep_constructed';
    if (edhGood) return 'keep_edh';
    if (edhOk) return 'maybe';
    return 'drop';
  },

  // ============================================================
  // 查询
  // ============================================================

  /**
   * 获取单张卡牌完整信息（大小写不敏感）
   * @returns {Object|null} 格式化后的卡牌数据
   */
  getCard(name) {
    // 精确匹配
    if (this.cards[name]) {
      return this._formatCard(this.cards[name]);
    }
    // 大小写不敏感匹配
    const lower = name.toLowerCase();
    if (this.nameIndex[lower]) {
      return this._formatCard(this.cards[this.nameIndex[lower]]);
    }
    return null;
  },

  /**
   * 模糊搜索卡名（英文 + 中文）
   * @param {string} query - 搜索词
   * @param {number} limit - 返回数量上限
   * @returns {Array} 格式化后的卡牌列表
   */
  search(query, limit = 15) {
    query = query.trim().toLowerCase();
    if (!query) return [];

    const results = [];
    for (const [name, card] of Object.entries(this.cards)) {
      const nameLower = name.toLowerCase();
      const cn = card.chinese_name || '';
      let score = 0;

      // 精确匹配
      if (nameLower === query) {
        score = 100;
      }
      // 前缀匹配
      else if (nameLower.startsWith(query)) {
        score = 80;
      }
      // 包含匹配
      else if (nameLower.includes(query)) {
        score = 60;
      }
      // 中文匹配
      else if (cn && cn.toLowerCase().includes(query)) {
        score = 50;
      }
      // 模糊匹配（每个词都包含）
      else if (query.split(/\s+/).every(q => nameLower.includes(q))) {
        score = 40;
      }

      if (score > 0) {
        results.push({ score, name });
      }
    }

    results.sort((a, b) => {
      if (a.score !== b.score) return b.score - a.score;
      return a.name.localeCompare(b.name);
    });

    return results.slice(0, limit).map(r => this._formatCard(this.cards[r.name]));
  },

  /**
   * 数据库统计信息
   */
  stats() {
    let total = Object.keys(this.cards).length;
    let hasConstructed = 0;
    let hasEdh = 0;
    let hasChinese = 0;
    const tierCounts = {};
    const recCounts = {};

    for (const card of Object.values(this.cards)) {
      // 构筑数据
      const constructed = card.constructed || {};
      const used = Object.values(constructed).some(
        v => (v.count || 0) > 0 || (v.sideboard || 0) > 0
      );
      if (used) hasConstructed++;

      // EDH 数据
      if (card.edh) hasEdh++;

      // 中文名
      if (card.chinese_name) hasChinese++;

      // 等级分布（预计算 or 动态计算）
      const tier = this._getEdhTier(card);
      tierCounts[tier] = (tierCounts[tier] || 0) + 1;

      // 建议分布（预计算 or 动态计算）
      const rec = this._getRecommendation(card, tier, used);
      recCounts[rec] = (recCounts[rec] || 0) + 1;
    }

    return {
      total_cards: total,
      has_constructed: hasConstructed,
      has_edh: hasEdh,
      has_chinese_name: hasChinese,
      edh_tier_distribution: tierCounts,
      recommendation_distribution: recCounts,
    };
  },

  // ============================================================
  // 内部工具
  // ============================================================

  /**
   * 获取卡牌的 EDH 等级（优先用预计算值，否则动态计算）
   */
  _getEdhTier(card) {
    if (card.edh_tier) return card.edh_tier;
    if (card.edh) return this.classifyEdh(card.edh.num_decks, card.edh.inclusion);
    return 'unknown';
  },

  /**
   * 获取卡牌的保留建议（优先用预计算值，否则动态计算）
   */
  _getRecommendation(card, tier, constructedUsed) {
    if (card.recommendation) return card.recommendation;
    if (constructedUsed === undefined) {
      const constructed = card.constructed || {};
      constructedUsed = Object.values(constructed).some(
        v => (v.count || 0) > 0 || (v.sideboard || 0) > 0
      );
    }
    return this.recommend(constructedUsed, tier);
  },

  /**
   * 格式化卡牌数据（添加中文标签，与 Python _format_card 一致）
   * 支持两种数据格式：
   *   1. 完整版（含 edh_tier, recommendation 预计算字段）
   *   2. 压缩版（仅含原始数据，前端动态计算）
   */
  _formatCard(card) {
    const result = { ...card };

    // 稀有度中文
    result.rarity_cn = this.RARITY_CN[card.rarity] || card.rarity || '';

    // 颜色中文
    result.color_cn = this.COLOR_CN[card.color_category] || card.color_category || '';

    // EDH 等级
    const edhTier = this._getEdhTier(card);
    result.edh_tier = edhTier;
    result.edh_tier_label = (this.EDH_TIERS[edhTier] || this.EDH_TIERS.unknown).label;

    // 保留建议
    const rec = this._getRecommendation(card, edhTier);
    result.recommendation = rec;
    result.recommendation_label = (this.RECOMMENDATIONS[rec] || this.RECOMMENDATIONS.drop).label;
    result.recommendation_color = (this.RECOMMENDATIONS[rec] || this.RECOMMENDATIONS.drop).color;

    return result;
  },
};

// 导出供 ES Module 使用（可选）
if (typeof module !== 'undefined' && module.exports) {
  module.exports = CardKeeper;
}
