-- 쇼핑몰 운영팀에서 최근 재구매가 잘 일어나는 상품을 찾고 싶어한다.

/**
*상품번호
*상품명
*구매고객수(유효주문 기준)
*재구매고객수-같은 상품을 다른 주문에서 2회이상 구매한 고객
*재구매율
*재구매율 내림차순
*재구매율이 같으면 구매고객 내림차순
*상위 10개만 조회
*구매고객이 5명 미만인 상품은 제외
*/

-- 고객별 주문 상품을 먼저 구하자.
with pro_cus as (
	select o.customer_id
		 , p.product_id
		 , p."name" 
		 , count(distinct o.order_id) as cnt_procus
	  FROM products p
	  JOIN order_items oi on p.product_id =oi.product_id
	  join orders o on oi.order_id=o.order_id 
	 where o.status not in ('취소','환불')
	 group by o.customer_id, p.product_id
	 order by o.customer_id asc , p.product_id asc)
select pc.product_id as 품번
	 , pc."name" as 상품명
	 , count(*) as 구매고객수
	 , count(*) filter (where pc.cnt_procus>=2) as "2회이상구매자수"
	 , round(100.0*count(*) filter (where pc.cnt_procus>=2)/count(*),2) as 재구매율
  from pro_cus pc
 group by pc.product_id, pc."name"
having count(*)>=5
 order by 재구매율 desc, 구매고객수 asc
 limit 10;

--카테고리별로 최근 구매려깅 떨어지고 있는지 확인하고 싶습니다.

/*
 * 카테고리번호
 * 카테고리명
 * 최근 3개월 매출
 * 직전 3개월 매출
 * 증감률
 */

select c.category_id as 분류번호
	 , c."name" as 이름
	 , to_char(date_trunc('quarter',o.order_date),'yyyy"Q"q') as 분기
	 , sum(oi.quantity * oi.unit_price) as 분기매출
	 , lag(sum(oi.quantity * oi.unit_price)) over(partition by c.category_id order by date_trunc('quarter',o.order_date) asc) as 직전분기매출
	 , round(100.0*(sum(oi.quantity * oi.unit_price)-
	   lag(sum(oi.quantity * oi.unit_price)) over(partition by c.category_id order by date_trunc('quarter',o.order_date) asc))/
	   lag(sum(oi.quantity * oi.unit_price)) over(partition by c.category_id order by date_trunc('quarter',o.order_date) asc),2) as 증감율
  from categories c  
  join products p on p.category_id =c.category_id 
  join order_items oi on oi.product_id =p.product_id 
  join orders o on oi.order_id =o.order_id 
 where o.status not in ('취소','환불')
 group by c.category_id , c."name",
 	   date_trunc('quarter',o.order_date)
 order by c.category_id asc, date_trunc('quarter',o.order_date) asc
 
 
 with amount_month as(
	 select c.category_id 
		 , c."name"
		 , date_trunc('month',o.order_date)::date as month_
		 , sum(oi.quantity *oi.unit_price) as amount_
		 , max(date_trunc('month',o.order_date)::date) over() as max_date
	  from categories c  
	  join products p on p.category_id =c.category_id 
	  join order_items oi on oi.product_id =p.product_id 
	  join orders o on oi.order_id =o.order_id 
	 where o.status not in ('취소','환불')
	 group by c.category_id , c."name",
	 	   date_trunc('month',o.order_date)
	 order by c.category_id asc, date_trunc('month',o.order_date) asc)
select am.category_id 
	 , am."name" 
	 , case when am.max_date <= am.month_+interval '3 months' then '현재3개월매출'
	   else '직전3개월매출'
	   end as 기간
	 , sum(am.amount_)
	 , lag(sum(am.amount_)) over(partition by am.category_id)
	 , round(100.0*(sum(am.amount_)-lag(sum(am.amount_)) over(partition by am.category_id order by am.category_id asc))/
	 lag(sum(am.amount_)) over(partition by am.category_id order by am.category_id asc),2)
  from amount_month am
 where am.max_date<=am.month_+interval '6 months'
 group by am.category_id,am."name", 3 
 order by am.category_id asc, 3 desc 
 
 ----------
 
with amount_month as (
    select c.category_id
         , c."name"
         , date_trunc('month', o.order_date)::date as month_
         , sum(oi.quantity * oi.unit_price) as amount_
      from categories c
      join products p on p.category_id = c.category_id
      join order_items oi on oi.product_id = p.product_id
      join orders o on oi.order_id = o.order_id
     where o.status not in ('취소', '환불')
     group by c.category_id, c."name", date_trunc('month', o.order_date)::date
),
max_month as (
    select max(month_) as max_month
      from amount_month
)
select am.category_id
     , am."name"
     , sum(am.amount_) filter (
           where am.month_ > mm.max_month - interval '3 months'
       ) as 최근3개월매출
     , sum(am.amount_) filter (
           where am.month_ <= mm.max_month - interval '3 months'
             and am.month_ >  mm.max_month - interval '6 months'
       ) as 직전3개월매출
     , round(
           100.0 *
           (
             sum(am.amount_) filter (
                 where am.month_ > mm.max_month - interval '3 months'
             )
             -
             sum(am.amount_) filter (
                 where am.month_ <= mm.max_month - interval '3 months'
                   and am.month_ >  mm.max_month - interval '6 months'
             )
           )
           / nullif(
               sum(am.amount_) filter (
                   where am.month_ <= mm.max_month - interval '3 months'
                     and am.month_ >  mm.max_month - interval '6 months'
               ),
               0
           )
       , 2) as 증감률
  from amount_month am
  cross join max_month mm
 group by am.category_id, am."name"
having sum(am.amount_) filter (
           where am.month_ > mm.max_month - interval '3 months'
       ) is not null
 order by 증감률 desc;