export interface ProductSpec {
  id: string
  label: string
  price: number
  quantity: number
  unit: string
}

export interface ShoppingProduct {
  name: string
  sku: string
  specs: ProductSpec[]
  kind: 'fresh' | 'staple'
}

const freshSpec = (id: string, label: string, price: number, quantity: number, unit: string): ProductSpec => ({
  id,
  label,
  price,
  quantity,
  unit,
})

const stapleSpec = (id: string, label: string, price: number, quantity: number, unit: string): ProductSpec => ({
  id,
  label,
  price,
  quantity,
  unit,
})

export function buildFreshProduct(name: string, recipeAmount: string): ShoppingProduct {
  const text = name || ''
  if (text.includes('鱼') || text.includes('虾') || text.includes('蟹')) {
    return {
      name: text,
      sku: text.includes('虾') ? `${text} 一份` : `${text} 一条`,
      kind: 'fresh',
      specs: [
        freshSpec('small', '1条（约1–1.5斤）', 18.8, 1, '条'),
        freshSpec('large', '1条（约2斤）', 28.8, 1, '条'),
      ],
    }
  }
  if (text.includes('葱')) {
    return {
      name: text,
      sku: text.includes('大葱') ? '大葱一根（约150g）' : '香葱一把（约100g）',
      kind: 'fresh',
      specs: [freshSpec('one', text.includes('大葱') ? '1根（约150g）' : '1把（约100g）', text.includes('大葱') ? 3.2 : 2.8, 1, text.includes('大葱') ? '根' : '把')],
    }
  }
  if (text.includes('姜')) {
    return { name: text, sku: '生姜一块（约100g）', kind: 'fresh', specs: [freshSpec('one', '1块（约100g）', 3.5, 1, '块')] }
  }
  if (text.includes('蒜')) {
    return { name: text, sku: '大蒜一头（约50g）', kind: 'fresh', specs: [freshSpec('one', '1头（约50g）', 2.5, 1, '头')] }
  }
  if (text.includes('鸡蛋') || text.includes('鸭蛋')) {
    return {
      name: text,
      sku: `${text} 一盒`,
      kind: 'fresh',
      specs: [
        freshSpec('small', '10枚装', 9.9, 10, '个'),
        freshSpec('large', '20枚装', 17.9, 20, '个'),
      ],
    }
  }
  if (text.includes('肉') || text.includes('排') || text.includes('鸡')) {
    return {
      name: text,
      sku: `${text} 一份`,
      kind: 'fresh',
      specs: [
        freshSpec('small', '约300g', 15.8, 300, 'g'),
        freshSpec('large', '约500g', 24.8, 500, 'g'),
      ],
    }
  }
  if (text.includes('奶')) {
    return { name: text, sku: `${text} 一盒（250ml）`, kind: 'fresh', specs: [freshSpec('one', '1盒（250ml）', 4.5, 1, '盒')] }
  }
  if (['番茄', '西红柿', '土豆', '黄瓜', '茄子'].some((word) => text.includes(word))) {
    return {
      name: text,
      sku: `${text} 一份`,
      kind: 'fresh',
      specs: [
        freshSpec('small', '约500g', 4.8, 500, 'g'),
        freshSpec('large', '约1kg', 8.8, 1000, 'g'),
      ],
    }
  }
  if (['菜', '菠菜', '西兰花', '菌', '菇'].some((word) => text.includes(word))) {
    return {
      name: text,
      sku: `${text} 一把/一份`,
      kind: 'fresh',
      specs: [
        freshSpec('small', '约500g', 5.8, 500, 'g'),
        freshSpec('large', '约1kg', 9.9, 1000, 'g'),
      ],
    }
  }
  return {
    name: text,
    sku: `${text} 一份`,
    kind: 'fresh',
    specs: [freshSpec('default', '约1份', 8.0, 1, '份')],
  }
}

const BOTTLE_WORDS = ['油', '酱油', '生抽', '老抽', '蚝油', '醋', '料酒', '香油', '蒸鱼豉油']
const BAG_WORDS = ['盐', '糖', '淀粉', '胡椒', '花椒', '味精', '鸡精', '咖喱', '五香粉', '十三香']

export function buildStapleProduct(name: string): ShoppingProduct {
  const isBottle = BOTTLE_WORDS.some((word) => name.includes(word))
  if (isBottle) {
    return {
      name,
      sku: `${name} 一瓶`,
      kind: 'staple',
      specs: [
        stapleSpec('small', '小瓶装（约250ml）', 6.9, 250, 'ml'),
        stapleSpec('family', '家庭装（约500ml）', 12.9, 500, 'ml'),
      ],
    }
  }
  const isBag = BAG_WORDS.some((word) => name.includes(word))
  if (isBag) {
    return {
      name,
      sku: `${name} 一袋`,
      kind: 'staple',
      specs: [
        stapleSpec('small', '小包装（约200g）', 3.5, 200, 'g'),
        stapleSpec('family', '家庭装（约500g）', 7.9, 500, 'g'),
      ],
    }
  }
  return {
    name,
    sku: `${name} 一份`,
    kind: 'staple',
    specs: [stapleSpec('default', '家庭装', 9.9, 1, '份')],
  }
}

export function formatPrice(value: number): string {
  return `￥${value.toFixed(2)}`
}

export function specLabel(spec: ProductSpec): string {
  return `${spec.label} · ${formatPrice(spec.price)}`
}

export function orderLabel(product: ShoppingProduct, spec: ProductSpec, usage = ''): string {
  // 生鲜按包装规格下单；菜谱用量只用于展示。
  if (product.kind === 'fresh' && spec.unit === '条') return `${product.name} ${spec.quantity}条`
  if (product.kind === 'fresh' && spec.unit === '把') return `${product.name} ${spec.quantity}把`
  if (product.kind === 'fresh' && spec.unit === '根') return `${product.name} ${spec.quantity}根`
  if (product.kind === 'fresh' && spec.unit === '块') return `${product.name} ${spec.quantity}块`
  if (spec.unit === 'ml') return `${product.name} ${spec.quantity}ml`
  return `${product.name} ${spec.quantity}${spec.unit}`
}
