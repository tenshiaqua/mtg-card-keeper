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

  cards: {},       // { cardName: cardData }
  nameIndex: {},   // { lowercase_name: original_name } 用于大小写不敏感搜索
  _loaded: false,

  // ============================================================
  // 初始化
  // ============================================================

  /**
   * 加载数据库 JSON
   * @param {string} jsonPath - card_database.json 路径
   */
  async init(jsonPath) {
    const resp = await fetch(jsonPath);
    if (!resp.ok) {
      throw new Error(`加载数据库失败: ${resp.status} ${resp.statusText}`);
    }
    this.cards = await resp.json();
    this.buildIndex();
    this._loaded = true;
  },

  buildIndex() {
    this.nameIndex = {};
    for (const name of Object.keys(this.cards)) {
      this.nameIndex[name.toLowerCase()] = name;
    }
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
