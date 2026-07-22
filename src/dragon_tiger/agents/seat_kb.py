"""知名席位知识库 - A股龙虎榜常见资金席位识别

维护说明:
- 关键词用于模糊匹配营业部名称中包含该字符串的席位
- style: 资金属性分类
- tag: 操作风格/策略标签
- win_rate: 历史胜率评估（基于公开龙虎榜数据统计）
- note: 备注说明（选填）

知识库来源：公开龙虎榜历史数据统计、财经媒体报道、社区公认认知。
仅供学习研究使用，不构成投资建议。
"""

# ==================== 顶级游资席位 ====================
TOP_YZ = {
    "南京太平南路": {"style": "顶级游资", "tag": "龙头战法", "win_rate": "高", "note": "赵老哥/章建平"},
    "溧阳路": {"style": "顶级游资", "tag": "题材挖掘", "win_rate": "高", "note": "知名游资聚集"},
    "华鑫上海宛平南路": {"style": "顶级游资", "tag": "趋势接力", "win_rate": "高", "note": "炒股养家"},
    "中国银河绍兴": {"style": "顶级游资", "tag": "龙头战法", "win_rate": "高", "note": "赵老哥关联"},
    "国泰君安上海江苏路": {"style": "顶级游资", "tag": "龙头低吸", "win_rate": "高", "note": "章建平"},
    "东方证券上海浦东新区南泉北路": {"style": "顶级游资", "tag": "短线接力", "win_rate": "高", "note": "作手新一"},
    "华泰深圳益田路荣超商务中心": {"style": "顶级游资", "tag": "题材炒作", "win_rate": "中高", "note": "深圳帮"},
    "中信上海牡丹江路": {"style": "顶级游资", "tag": "波段操作", "win_rate": "中高", "note": "许昌系"},
    "中泰深圳欢乐海岸": {"style": "顶级游资", "tag": "打板龙头", "win_rate": "中高", "note": "欢乐海岸"},
    "招商深圳蛇口工业七路": {"style": "顶级游资", "tag": "题材快进快出", "win_rate": "中高"},
    "中信上海溧阳路": {"style": "顶级游资", "tag": "题材挖掘", "win_rate": "高", "note": "一线游资聚集"},
    "东方财富拉萨东环路第二": {"style": "散户大本营", "tag": "散户集中营", "win_rate": "低", "note": "东财拉萨天团"},
    "东方财富拉萨团结路第二": {"style": "散户大本营", "tag": "散户集中营", "win_rate": "低", "note": "东财拉萨天团"},
    "东方财富拉萨金融城南环路": {"style": "散户大本营", "tag": "散户集中营", "win_rate": "低", "note": "东财拉萨天团"},
    "东方财富拉萨": {"style": "散户大本营", "tag": "散户集中营", "win_rate": "低"},
}

# ==================== 一线游资席位 ====================
FIRST_YZ = {
    "财通杭州上塘路": {"style": "一线游资", "tag": "打板", "win_rate": "中高", "note": "杭州帮"},
    "国盛宁波桑田路": {"style": "一线游资", "tag": "短线", "win_rate": "中高", "note": "桑田路"},
    "华泰天津二纬路": {"style": "一线游资", "tag": "短线", "win_rate": "中高"},
    "国信深圳泰然九路": {"style": "一线游资", "tag": "波段", "win_rate": "中高", "note": "深圳帮"},
    "华鑫上海分公司": {"style": "一线游资", "tag": "多策略", "win_rate": "中高"},
    "华鑫佛山南海大道": {"style": "一线游资", "tag": "短线", "win_rate": "中"},
    "华泰上海武定路": {"style": "一线游资", "tag": "打板", "win_rate": "中高"},
    "中信建投北京朝阳区": {"style": "一线游资", "tag": "题材", "win_rate": "中高"},
    "中信建投北京中关村": {"style": "一线游资", "tag": "科技成长", "win_rate": "中高"},
    "国联上海分公司": {"style": "一线游资", "tag": "多策略", "win_rate": "中"},
    "中信上海分公司": {"style": "一线游资", "tag": "多策略", "win_rate": "中高"},
    "中信建投北京东三环": {"style": "一线游资", "tag": "波段", "win_rate": "中高"},
    "中金公司上海分公司": {"style": "一线游资", "tag": "多策略", "win_rate": "中高"},
    "东方证券上海浦东新区崮山路": {"style": "一线游资", "tag": "短线", "win_rate": "中高"},
    "华泰成都蜀金路": {"style": "一线游资", "tag": "题材", "win_rate": "中", "note": "成都帮"},
    "华泰南昌红谷中大道": {"style": "一线游资", "tag": "短线", "win_rate": "中"},
    "财通温岭中华路": {"style": "一线游资", "tag": "短线", "win_rate": "中", "note": "温州帮"},
    "华福泉州丰泽街": {"style": "一线游资", "tag": "短线", "win_rate": "中", "note": "泉州帮"},
    "国泰海通上海分公司": {"style": "一线游资", "tag": "多策略", "win_rate": "中高"},
    "中信山东淄博": {"style": "一线游资", "tag": "短线", "win_rate": "中"},
}

# ==================== 量化私募席位 ====================
QUANT_FUND = {
    "华泰证券总部": {"style": "量化私募", "tag": "程序化交易", "win_rate": "中", "note": "量化通道"},
    "中信建投北京东城": {"style": "量化私募", "tag": "程序化交易", "win_rate": "中"},
    "国泰君安上海分公司": {"style": "量化私募", "tag": "量化多策略", "win_rate": "中"},
    "中泰上海建国中路": {"style": "量化私募", "tag": "高频", "win_rate": "中"},
    "国金上海互联网": {"style": "量化私募", "tag": "程序化交易", "win_rate": "中"},
    "中信建投北京朝外大街": {"style": "量化私募", "tag": "量化", "win_rate": "中"},
    "华泰苏州人民路": {"style": "量化私募", "tag": "量化", "win_rate": "中"},
    "平安深圳深南东路": {"style": "量化私募", "tag": "量化", "win_rate": "中"},
    "申万宏源上海": {"style": "量化私募", "tag": "程序化交易", "win_rate": "中"},
    "中信证券总部": {"style": "量化私募", "tag": "多策略", "win_rate": "中高"},
}

# ==================== 外资机构席位 ====================
FOREIGN_INST = {
    "高盛": {"style": "外资机构", "tag": "QFII/自营", "win_rate": "中高", "note": "Goldman Sachs"},
    "摩根士丹利": {"style": "外资机构", "tag": "QFII/自营", "win_rate": "中高", "note": "Morgan Stanley"},
    "摩根大通": {"style": "外资机构", "tag": "QFII/自营", "win_rate": "中高", "note": "JPMorgan"},
    "瑞银证券": {"style": "外资机构", "tag": "QFII", "win_rate": "中高", "note": "UBS"},
    "瑞银": {"style": "外资机构", "tag": "QFII", "win_rate": "中高", "note": "UBS"},
    "花旗": {"style": "外资机构", "tag": "QFII", "win_rate": "中", "note": "Citibank"},
    "汇丰": {"style": "外资机构", "tag": "QFII", "win_rate": "中", "note": "HSBC"},
    "德意志银行": {"style": "外资机构", "tag": "QFII", "win_rate": "中", "note": "Deutsche Bank"},
    "法国巴黎银行": {"style": "外资机构", "tag": "QFII", "win_rate": "中", "note": "BNP Paribas"},
    "野村证券": {"style": "外资机构", "tag": "QFII", "win_rate": "中", "note": "Nomura"},
    "大和证券": {"style": "外资机构", "tag": "QFII", "win_rate": "中", "note": "Daiwa"},
    "瑞士信贷": {"style": "外资机构", "tag": "QFII", "win_rate": "中", "note": "Credit Suisse"},
    "巴克莱银行": {"style": "外资机构", "tag": "QFII", "win_rate": "中", "note": "Barclays"},
    "渣打银行": {"style": "外资机构", "tag": "QFII", "win_rate": "中", "note": "Standard Chartered"},
}

# ==================== 北向资金通道 ====================
NORTHBOUND = {
    "沪股通专用": {"style": "北向资金", "tag": "外资配置", "win_rate": "中"},
    "深股通专用": {"style": "北向资金", "tag": "外资配置", "win_rate": "中"},
}

# ==================== 机构席位 ====================
INSTITUTION = {
    "机构专用": {"style": "机构", "tag": "公募/社保/险资", "win_rate": "中高"},
}

# ==================== 汇总（按匹配优先级排列） ====================
KNOWN_SEATS: dict[str, dict] = {}
for d in [TOP_YZ, FIRST_YZ, QUANT_FUND, FOREIGN_INST, NORTHBOUND, INSTITUTION]:
    KNOWN_SEATS.update(d)

# 统计信息
SEAT_STATS = {
    "顶级游资": len(TOP_YZ),
    "一线游资": len(FIRST_YZ),
    "量化私募": len(QUANT_FUND),
    "外资机构": len(FOREIGN_INST),
    "北向资金": len(NORTHBOUND),
    "机构": len(INSTITUTION),
    "总计": len(KNOWN_SEATS),
}