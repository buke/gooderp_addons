# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import fields, models, api, tools

class supplier_statements_report(models.Model):
    _name = "supplier.statements.report"
    _description = u"供应商对账单"
    _auto = False
    _order = 'date'

    @api.one
    @api.depends('amount', 'pay_amount', 'partner_id')
    def _compute_balance_amount(self):
        pre_record = self.search([('id', '=', self.id - 1), ('partner_id', '=', self.partner_id.id)])
        # 相邻的两条记录，partner不同，应收款余额重新计算
        if pre_record:
            if pre_record.name != '期初余额':
                before_balance = pre_record.balance_amount
            else:
                before_balance = pre_record.amount
        else:
            before_balance = 0
        self.balance_amount += before_balance + self.amount - self.pay_amount

    partner_id = fields.Many2one('partner', string=u'业务伙伴', readonly=True)
    name = fields.Char(string=u'单据编号', readonly=True)
    date = fields.Date(string=u'单据日期', readonly=True)
    purchase_amount = fields.Float(string=u'采购金额', readonly=True)
    benefit_amount = fields.Float(string=u'优惠金额', readonly=True)
    amount = fields.Float(string=u'应付金额', readonly=True)
    pay_amount = fields.Float(string=u'实际付款金额', readonly=True)
    balance_amount = fields.Float(string=u'应付款余额', compute='_compute_balance_amount', readonly=True)
    note = fields.Char(string=u'备注', readonly=True)
    move_id = fields.Many2one('wh.move', string=u'出入库单', readonly=True)

    def init(self, cr):
        # union money_order(type = 'pay'), money_invoice(type = 'expense')
        tools.drop_view_if_exists(cr, 'supplier_statements_report')
        cr.execute("""
            CREATE or REPLACE VIEW supplier_statements_report AS (
            SELECT  ROW_NUMBER() OVER(ORDER BY partner_id,date) AS id,
                    partner_id,
                    name,
                    date,
                    purchase_amount,
                    benefit_amount,
                    amount,
                    pay_amount,
                    balance_amount,
                    note,
                    move_id
            FROM
                (SELECT go.partner_id AS partner_id,
                        '期初余额' AS name,
                        go.date AS date,
                        0 AS purchase_amount,
                        0 AS benefit_amount,
                        go.payable AS amount,
                        0 AS pay_amount,
                        0 AS balance_amount,
                        Null AS note,
                        0 AS move_id
                FROM go_live_order AS go
                LEFT JOIN partner AS p ON go.partner_id = p.id
                LEFT JOIN core_category AS c ON p.s_category_id = c.id
                WHERE c.type = 'supplier'
                UNION ALL
                SELECT m.partner_id,
                        m.name,
                        m.date,
                        0 AS purchase_amount,
                        0 AS benefit_amount,
                        0 AS amount,
                        m.amount AS pay_amount,
                        0 AS balance_amount,
                        m.note,
                        NULL AS move_id
                FROM money_order AS m
                WHERE m.type = 'pay'
                UNION ALL
                SELECT  mi.partner_id,
                        mi.name,
                        mi.date,
                        br.amount + br.discount_amount AS purchase_amount,
                        br.discount_amount AS benefit_amount,
                        mi.amount,
                        0 AS pay_amount,
                        0 AS balance_amount,
                        Null AS note,
                        mi.move_id
                FROM money_invoice AS mi
                LEFT JOIN core_category AS c ON mi.category_id = c.id
                JOIN buy_receipt AS br ON br.buy_move_id = mi.move_id
                WHERE c.type = 'expense'
                ) AS ps)
        """)

    @api.multi
    def find_source_order(self):
        # 查看源单，两种情况：收付款单、采购入库单
        money = self.env['money.order'].search([('name', '=', self.name)])
        # 付款单
        if money:
            view = self.env.ref('money.money_order_form')
            return {
                'name': u'付款单',
                'view_type': 'form',
                'view_mode': 'form',
                'view_id': False,
                'views': [(view.id, 'form')],
                'res_model': 'money.order',
                'type': 'ir.actions.act_window',
                'res_id': money.id,
                'context': {'type': 'pay'}
            }

        # 采购入库单
        buy = self.env['buy.receipt'].search([('name', '=', self.name)])
        view = self.env.ref('buy.buy_receipt_form')

        return {
            'name': u'采购入库单',
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': False,
            'views': [(view.id, 'form')],
            'res_model': 'buy.receipt',
            'type': 'ir.actions.act_window',
            'res_id': buy.id,
            'context': {'type': 'pay'}
        }

class supplier_statements_report_with_goods(models.TransientModel):
    _name = "supplier.statements.report.with.goods"
    _description = u"供应商对账单带商品明细"

    partner_id = fields.Many2one('partner', string=u'业务伙伴', readonly=True)
    name = fields.Char(string=u'单据编号', readonly=True)
    date = fields.Date(string=u'单据日期', readonly=True)
    category_id = fields.Many2one('core.category', u'商品类别')
    goods_code = fields.Char(u'商品编号')
    goods_name = fields.Char(u'商品名称')
    attribute_id = fields.Many2one('attribute', u'规格型号')
    uom_id = fields.Many2one('uom', u'单位')
    quantity = fields.Float(u'数量')
    price = fields.Float(u'单价')
    discount_amount = fields.Float(u'折扣额')
    without_tax_amount = fields.Float(u'不含税金额')
    tax_amount = fields.Float(u'税额')
    order_amount = fields.Float(string=u'采购金额', readonly=True)  # 采购
    benefit_amount = fields.Float(string=u'优惠金额', readonly=True)
    fee = fields.Float(string=u'客户承担费用', readonly=True)
    amount = fields.Float(string=u'应付金额', readonly=True)
    pay_amount = fields.Float(string=u'实际付款金额', readonly=True)
    balance_amount = fields.Float(string=u'应付款余额', readonly=True)
    note = fields.Char(string=u'备注', readonly=True)
    move_id = fields.Many2one('wh.move', string=u'出入库单', readonly=True)

    @api.multi
    def find_source_order(self):
        # 查看源单，两种情况：付款单、采购入库单
        money = self.env['money.order'].search([('name', '=', self.name)])
        if money:  # 付款单
            view = self.env.ref('money.money_order_form')
            return {
                'name': u'付款单',
                'view_type': 'form',
                'view_mode': 'form',
                'view_id': False,
                'views': [(view.id, 'form')],
                'res_model': 'money.order',
                'type': 'ir.actions.act_window',
                'res_id': money.id,
                'context': {'type': 'pay'}
            }

        # 采购入库单
        buy = self.env['buy.receipt'].search([('name', '=', self.name)])
        view = self.env.ref('buy.buy_receipt_form')
        return {
            'name': u'采购入库单',
            'view_type': 'form',
            'view_mode': 'form',
            'view_id': False,
            'views': [(view.id, 'form')],
            'res_model': 'buy.receipt',
            'type': 'ir.actions.act_window',
            'res_id': buy.id,
            'context': {'type': 'pay'}
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
