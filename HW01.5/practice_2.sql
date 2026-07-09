-- 1. 취소 환불을 제외한 전체 유효주문 건수와 유효매출 합계를 한 행으로 구하라
select count(*) as total_cnt
	 , sum(o.total_amount) as GMV
  from orders o 
 where o.status not in ('취소','환불');


 -- 2. 주문상태별 주문건수, 전체 대비 비율, 매출을 건수 내림차순으로 구하라
select o.status as order_status
	 , count(*) as status_count
	 , round(100*count(*)/sum(count(*)) over(),1) as per_status
	 , sum(o.total_amount) as status_amount
  from orders o 
 group by o.status 
 order by 2 desc 
;

-- 3 회원 등급별 회원수와 전체 대비 비율(%)을 회원 수 내림차순으로 구하라
select c.grade
	 , count(*) as grade_customers
	 , round(100.0*(count(*)/sum(count(*)) over()),1) as grade_ratio
  from customers c 
 group by c.grade 
 order by count(*) desc;

--4. 활성 / 휴면(is_active) 회원수와 비율(%)을 구하라
select case when c.is_active then '활성'
			else '휴면'
			end as 회원상태
	 , count(*) as 회원수
	 , round(count(*) / sum(count(*)) over()*100.0,1) as 비율 
  from customers c 
 group by c.is_active
 order by 1 asc ;
 
 
 --5.회원 수가 가장 많은 상위 10개 도시를 회원수와 함께 구하라
select c.city 
	 , count(*) as customers_cnt
  from customers c 
 group by c.city 
 order by count(*) desc, c.city asc
 limit 10;


 --6.가입연도별 신규 회원 수를 오름차순으로 구하라
select extract('year' from c.signup_date)::int as signup_year
	 , count(*)
  from customers c 
 group by extract('year' from c.signup_date)
 order by signup_year asc;


--7 상품 상태별(판매중/품절/단종) 상품수와 비율을 구하라
select p.status as products_status
	 , count(*)
	 , 100.0 * round(count(*) / sum(count(*)) over(),4) as status_ratio
  from products p 
 where p.status in ('판매중','품절','단종')
 group by p.status
 order by count(*) desc;
 
--8. 5만 / 10만 / 20만/ 30만 경계로 가격대를 5구간으로 나눠 구간별 상품수를 구하라
select case when p.price<50000 then '1.저가'
	   when p.price<100000 then '2.중저가'
	   when p.price<200000 then '3.중가'
	   when p.price<300000 then '4.중고가'
	   else '5.고가'
	   end as 가격대
	 , count(*)  
	 from products p 
 group by 가격대
 order by 1 asc;


--9. 카테고리별 매출과 판매수량을 매출 내림차순으로 구하라(취소 환불 제외) 
select p.category_id as category_num
	 , c."name" as category_name
	 , sum(oi.quantity) as sales_quantity
	 , sum(oi.quantity *oi.unit_price) as selling_amount 
  from products p 
  join order_items oi on p.product_id =oi.product_id 
  join categories c on c.category_id = p.category_id 
  join orders o on o.order_id =oi.order_id 
 where o.status not in ('취소','환불')
 group by p.category_id, c."name"  
 order by selling_amount desc, p.category_id asc;
 
 --10. 판매수량 기준 베스트 셀러 상품 top 10을 구하라
select p.product_id as 품번
	 , p."name" as 이름
	 , sum(oi.quantity) as 판매수량
	 , dense_rank() over(order by sum(oi.quantity) desc) as 순위
  from products p 
  join order_items oi on p.product_id =oi.product_id 
 group by p.product_id , p."name" 
 order by 순위 asc, p.product_id 
 limit 10;

-- 11. 매출액 효자 상품 TOP 10을 구하라
select p.product_id as 품번
	 , p."name" as 이름
	 , sum(oi.unit_price *oi.quantity) as 매출액
	 , rank() over(order by sum(oi.unit_price *oi.quantity) desc)as 효자매출
  from products p 
  join order_items oi on p.product_id =oi.product_id 
 group by p.product_id,p."name" 
 order by 효자매출 asc, 품번 asc
 limit 10;
 -- 12. 월 별 주문 건수와 매출을 시간순으로 구하라
select to_char(date_trunc('month',o.order_date)::date,'YYYY-MM') as month_
	 , count(*) as order_cnt
	 , sum(o.total_amount) as month_amount
  from orders o 
 where o.status not in ('취소', '환불')
 group by date_trunc('month',o.order_date)::date 
 order by month_ asc;


-- 요일 (일 ~토) 별 주문 건수와 매출을 요일 순서대로 구하라
select case when Extract(DOW from o.order_date)= 0 then '일'
			when Extract(DOW from o.order_date)= 1 then '월'
			when Extract(DOW from o.order_date)= 2 then '화'
			when Extract(DOW from o.order_date)= 3 then '수'
			when Extract(DOW from o.order_date)= 4 then '목'
			when Extract(DOW from o.order_date)= 5 then '금'
			else '토'
			end as 요일
	 , count(*) as 주문건수
	 , sum(o.total_amount) as 요일별매출
  from orders o
 group by Extract(DOW from o.order_date)
 order by Extract(DOW from o.order_date) asc
;

--시(0~23)간대별 주문건수 상위 10개를 구하라
select extract('hour' from o.order_date) as hours
	 , count(*) as order_cnt
  from orders o 
 group by extract('hour' from o.order_date)
 order by order_cnt desc
 limit 10
;

--배송지역(shipping_city)별 주문 건수·매출 상위 10개를 구하라.
select o.shipping_city as 도시
	 , count(*) as 주문건수
	 , sum(o.total_amount) as 매출
  from orders o
 where o.status not in ('취소','환불')
 group by o.shipping_city 
 order by sum(o.total_amount) desc, count(*) desc, o.shipping_city asc
 limit 10
;

-- 성별 x 카테고리별 매출을 성별 매출 내림차순으로 구하라
select c.gender as 성별
	 , p.category_id as 카테고리번호
	 , c2."name" as 카테고리명
	 , sum(oi.quantity *oi.unit_price) as 매출
  from order_items oi
  join orders o on oi.order_id = o.order_id 
  join customers c on o.customer_id =c.customer_id 
  join products p on p.product_id =oi.product_id 
  join categories c2 on c2.category_id =p.category_id 
 group by c.gender , p.category_id , c2."name"
 order by c.gender asc, 매출 desc;

-- 누적 유효 매출 상위 고객 20명을 이름·등급·주문수와 함께 구하라
select c."name" 
	 , count(distinct o.order_id) as order_cnt
	 , c.grade as customer_grade
	 , sum(o.total_amount) as total_amount
  from customers c
  JOIN orders o on c.customer_id = o.customer_id 
 where o.status not in ('취소','환불')
 group by c.customer_id, c."name" , c.grade 
 order by sum(o.total_amount) desc
 limit 20
 ;

-- 회원등급 별 주문 건수와 평균 객단가를 객단가 내림차순으로 구하라
select c.grade 
	 , count(distinct o.order_id) as 주문건수
	 , round(avg(o.total_amount),2) as 객단가
  from customers c
  join orders o on c.customer_id = o.customer_id 
 where o.status not in ('취소', '환불')
 group by c.grade
 order by 3 desc;
 
 
 
 -- 2회 이상 구매한 재구매 고객 수 , 전체 구매 고객수, 재구매율을 구하라
with count_orders as(
select o.customer_id 
	 , count(*) as count_buy
  from orders o
 group by o.customer_id)
select count(*) filter(where co.count_buy>=2) as rebuy_count
	 , count(*)
	 , round(100.0*count(*) filter(where co.count_buy>=2)/count(*),2) as rebuy_ratio
  from count_orders co
  
  -- 수정안한 답
  with count_orders as
  ( select o.customer_id , count(*) as count_buy 
  	     , count(*) over() as all_count 
  	  from orders o 
  	 group by o.customer_id 
  	 ) 
select count(*) as rebuy_count 
	 , co.all_count 
	 , round(100.0*count(*)/co.all_count,2) as rebuy_ratio 
  from count_orders co 
 where co.count_buy>=2 
 group by co.all_count;
 
 
-- 구매 횟수 구간(1회/2회/3회/4회/5회/6회+)별 고객수를 구하라
with ordercount as 
	 (select o.customer_id as member
	       , count(*) as order_count
        from orders o 
       group by o.customer_id )
select case when oc.order_count= 1 then '1회'
			when oc.order_count between 2 and 3 then'2,3회'
			when oc.order_count between 4 and 5 then'4,5회'
			when oc.order_count>=6 then '6회 이상'
			end as 주문수
	 , count(*) as "주문 고객수"
  from  ordercount oc
  group by 1
  order by 주문수 asc;
  
-- 고객별  RFM을 각 5분위 점수화하고 (RFM) 조합별 고객 수 상위 10개를 구하라
with RFM as (
	select o.customer_id 
		 , date_trunc('day',max(max(o.order_date)) over())-date_trunc('day',max(o.order_date)) as R_RFM --얼마나 최근에 구매했는가?
		 , count(*) as F_RFM --얼마나 많이 구매했는가
		 , sum(o.total_amount) as M_RFM
	  from orders o
	 where o.status not in ('취소','환불')
	 group by o.customer_id ),
customer_ntile as(
	select RFM.customer_id 
		 , RFM.r_rfm 
		 , ntile(5) over(order by r_rfm desc) as r점수
		 , RFM.f_rfm 
		 , ntile(5) over(order by f_rfm asc) as f점수
		 , RFM.m_rfm 
		 , ntile(5) over(order by m_rfm asc) as m점수
	  from RFM)
select cn.r점수
	 , cn.f점수
	 , cn.m점수
	 , count(*) as customer_count
  from customer_ntile cn
 group by r점수, f점수, m점수
 order by customer_count desc
 limit 10
;

--22, 월별 매출을 신규고객 과 기존고객 으로 나눠 구하라
select date_trunc('month',o.order_date)::date
	 , sum(o.total_amount) filter(where date_trunc('month',o.order_date)=date_trunc('month',c.signup_date))
	 , sum(o.total_amount) filter(where date_trunc('month',o.order_date)!=date_trunc('month',c.signup_date))
  from orders o
  join customers c on c.customer_id =o.customer_id 
 group by date_trunc('month',o.order_date)::date, date_trunc('month',c.signup_date)::date;

 --답지
 with mindate as(
	 select o.customer_id  
	 	  ,	date_trunc('month',min(o.order_date))::date as signup_date
	   from orders o
	  where o.status not in('취소','환불')
	  group by o.customer_id)
 select date_trunc('month',o.order_date)::date
	 , sum(o.total_amount) filter(where date_trunc('month',o.order_date)=md.signup_date) as 신규매출액
	 , sum(o.total_amount) filter(where date_trunc('month',o.order_date)>md.signup_date) as 기존매출액
  from orders o
  join mindate md on md.customer_id = o.customer_id 
 where o.status not in('취소','환불') 
 group by date_trunc('month',o.order_date)::date
 ;
 
 
-- 첫 구매월 코호트 별 M0,M3,M6,M12 재구매 고객수를 구하라
with mindate as(
	 select o.customer_id  
	 	  ,	date_trunc('month',min(o.order_date))::date as first_buy_date
	   from orders o
	  where o.status not in('취소','환불')
	  group by o.customer_id),
m0_12 as(select md.first_buy_date
	 , o.customer_id 
	 , count(*) filter(where date_trunc('month',o.order_date)=md.first_buy_date) as m0
	 , count(*) filter(where date_trunc('month',o.order_date) 
	 	between md.first_buy_date+interval '1 month'  and md.first_buy_date+interval '3 month') as m3
	 , count(*) filter(where date_trunc('month',o.order_date) 
	 	between md.first_buy_date+interval '4 month' and md.first_buy_date+interval '6 month') as m6
	 , count(*) filter(where date_trunc('month',o.order_date) 
	 between md.first_buy_date+interval '7 month' and md.first_buy_date+interval '12 month') as m12
  from orders o
  join mindate md on o.customer_id = md.customer_id
 where o.status not in ('취소','환불')
 group by md.first_buy_date,o.customer_id)
select mm.first_buy_date
	 , count(*) filter(where m0>0) as m0고객
	 , count(*) filter(where m3>0) as m3고객
	 , count(*) filter(where m6>0) as m6고객
	 , count(*) filter(where m12>0) as m12고객
  from m0_12 mm
 group by mm.first_buy_date
 order by mm.first_buy_date asc
;

-- 마지막 주문 후, 180일 초과 + 누적 매출 100만원 이상인 이탈 위험 우수고객 20명을 구하라
with danger_people as (
	select o.customer_id 
		 , sum(o.total_amount) as sum_buy
		 , count(*) as order_count
		 , max(date_trunc('day',o.order_date)) as buyer_latest
		 , max(max(date_trunc('day',o.order_date))) over() as maxdate
	  from orders o
	 where o.status not in ('취소','환불')
	 group by o.customer_id )
select dp.customer_id
	 , c."name" 
	 , dp.sum_buy as 누적매출 
	 , dp.buyer_latest as 최종구매일
	 , dp.maxdate -dp.buyer_latest as 미구매일수
	 , dp.order_count
  from danger_people dp
  join customers c on c.customer_id = dp.customer_id 
 where sum_buy>=1000000
   and dp.buyer_latest + interval '180 day'< dp.maxdate 
 order by dp.buyer_latest asc, dp.sum_buy desc, dp.customer_id asc
 limit 20
;

--카테고리별 매출, 매출 비중, 누적비중을 매출 내림차순으로 구하라
with category_data as
(select c.category_id
	 , c."name" 
	 , sum(oi.quantity *oi.unit_price) as sum_cat
	 , round(100.0*sum(oi.quantity *oi.unit_price) / sum(sum(oi.quantity *oi.unit_price)) over(),2) as per_cat
  from categories c  
  join products p on c.category_id =p.category_id 
  join order_items oi on p.product_id = oi.product_id 
 group by c.category_id, c."name" 
 order by 3 desc, c.category_id asc)
select cd."name" 
	  , cd.category_id 
	  , cd.sum_cat 
	  , cd.per_cat 
	 , sum(cd.per_cat) 
	 	over(order by cd.per_cat desc)
  from category_data cd  
 order by cd.per_cat desc, cd.category_id asc;
 
 --카테고리 별 매출 1위 상품을 각 1개씩 구하라
select t.category_id
	 , t.category_name
	 , t.product_id
	 , t.product_name
	 , t.amount
	 , t.rnk
  from (select c.category_id 
	 , c."name"  as category_name
	 , p.product_id
	 , p."name" as product_name
	 , sum(oi.quantity*oi.unit_price) as amount 
	 , rank() over(partition by c.category_id order by sum(oi.quantity*oi.unit_price)) as rnk
  from categories c 
  join products p on c.category_id =p.category_id 
  join order_items oi on oi.product_id =p.product_id
  group by p.product_id, c.category_id)t
 where t.rnk =1
 order by t.category_id asc;
 
 -- 월별 매출과 전월 매출, 전월 대비 증감율을 구하라
select to_char(date_trunc('month',o.order_date),'yyyy-mm') 
 	 , sum(o.total_amount) as month_amount
 	 , lag(sum(o.total_amount)) over(order by date_trunc('month',o.order_date)) as last_month
 	 , round(100.0 *(sum(o.total_amount) -lag(sum(o.total_amount)) over(order by date_trunc('month',o.order_date)))/
 	   lag(sum(o.total_amount)) over(order by date_trunc('month',o.order_date)),2) as updown_percent
   from orders o
  group by date_trunc('month',o.order_date);
  
  --수정본
with month_amount as (select to_char(date_trunc('month',o.order_date),'yyyy-mm') as month_ 
 	 , sum(o.total_amount) as month_amount
  from orders o
  group by date_trunc('month',o.order_date))
select ma.month_, ma.month_amount
 	 , lag(ma.month_amount) over(order by ma.month_) as last_month
 	 , round(100.0 *(ma.month_amount -lag(ma.month_amount) over(order by ma.month_))/
 	   lag(ma.month_amount) over(order by month_),2) as updown_percent
  from month_amount ma
 order by ma.month_ asc ;
 
 -- 회원등급 별 구매 고객 수 1인당 평균 주문수 1인당 평균매출을 구하라
with customer_order as (select o.customer_id
	 , count(*) as cus_cnt
	 , sum(o.total_amount) as cus_sum
  from orders o  
 group by o.customer_id)
select c.grade 
	 , count(*) as puchase_user_cnt
	 , round(avg(co.cus_cnt),2) as grade_cnt_avg
	 , round(avg(co.cus_sum),2) as grade_amount_avg
  from customers c
  join customer_order co on c.customer_id = co.customer_id
 group by c.grade 
 order by avg(co.cus_cnt) desc;
 
 -- 연령대별 (10대이하~ 60대 이상) 주문수와 매출을 구하라
with age_mm as (select extract(year from age(now(),c.birth_date)) as age_
	 , count(distinct c.customer_id) as customer_cnt
	 , count(o.order_id) as order_count
	 , sum(o.total_amount) as total_sum_age
  from customers c 
  join orders o on c.customer_id = o.customer_id 
 group by extract(year from age(now(),c.birth_date)))
select case when am.age_<= 19 then '10대이하' 
	 		when am.age_<= 29 then '20대'
	 		when am.age_<= 39 then '30대'
	 		when am.age_<= 49 then '40대'
	 		when am.age_<= 59 then '50대'
	 		else '60대 이상'
	 		end as age_case
	 , sum(am.customer_cnt) as customer_cnt
	 , sum(am.order_count) as order_age_count
	 , sum(am.total_sum_age) as total_amount_ages
  from age_mm am
 group by 1
 order by 1 asc
;

-- 같은 주문에 함께 담긴 상품 쌍 상위 10개 (동시 구매 주문 수)를 구하라
select oi1.product_id
	 , oi2.product_id 
	 , count(*)
  from order_items oi1
  join order_items oi2 on oi1.product_id<oi2.product_id and oi1.order_id = oi2.order_id  
 group by oi1.product_id , oi2.product_id 
 order by count(*) desc
 limit 10;


-- 월별 매출과 전년 동월 매출, 전년 동월 대비 (YoY) 증감률을 구하라
select to_char(date_trunc('month',o.order_date),'yyyy-mm') as 월
	 , sum(o.total_amount) as 동월매출
	 , lag(sum(o.total_amount),12) over(order by date_trunc('month',o.order_date) asc) as 전년매출
	 , round(100.0* (sum(o.total_amount)-lag(sum(o.total_amount),12) over(order by date_trunc('month',o.order_date) asc))/
	 lag(sum(o.total_amount),12) over(order by date_trunc('month',o.order_date) asc),2) as 전년대비증감율 
  from orders o
 group by date_trunc('month',o.order_date)
 order by date_trunc('month',o.order_date) asc 
;
 -- 분기별 주문 건 수, 전체 대비 분기 비중(%)을 구하라
select to_char(date_trunc('quarter',o.order_date),'YYYY"Q"Q')
	 , count(*) as 분기별주문건
	 , round(100.0* count(*) / sum(count(*)) over(),2) 
  from orders o
 group by date_trunc('quarter',o.order_date)
 order by date_trunc('quarter',o.order_date) asc
;
-- 카테고리별 취소·환불 매출률(%)을 높은 순으로 구하라
select c.category_id 
	 , c."name" 
	 , sum(oi.quantity*oi.unit_price) as 매출액
	 , sum(oi.quantity*oi.unit_price) filter (where o.status in ('취소','환불')) as "취소 환불 매출액"
	 , round( 100.0* sum(oi.quantity*oi.unit_price) filter(where o.status in ('취소','환불')) / 
	   sum(oi.quantity*oi.unit_price),2) as 취소환불률
  from categories c 
  join products p on p.category_id =c.category_id 
  join order_items oi on oi.product_id = p.product_id 
  join orders o on o.order_id = oi.order_id 
 group by c.category_id , c."name"
 order by 취소환불률 desc , c."name" asc 
 ;

-- 일별 매출과 7일 이동 평균을 (앞 15일) 구하라
with date_sales as(select date_trunc('day',o.order_date)::date as date_
	 , sum(o.total_amount) as date_amount
  from orders o 
 group by date_trunc('day',o.order_date)::date)
select ds.date_
	 , ds.date_amount
	 , round(avg(ds.date_amount) over (order by ds.date_ rows between 6 preceding and current row),2) as move_avg7
   from date_sales ds
  order by ds.date_
  limit 15;
 
-- 월별 매출과 연도 내 누적 매출을 구하라
with month_info as
	(select date_trunc('month',o.order_date)::date as month_
		 , sum(o.total_amount) as month_amount
	  from orders o
	 group by date_trunc('month',o.order_date))
select to_char(mi.month_,'yyyy-mm') 
	 , mi.month_amount 
	 , sum(mi.month_amount) over (partition by date_trunc('year',mi.month_) order by mi.month_ asc)
  from month_info mi
 order by mi.month_ asc;

  	
 
 -- 월별 주문 수와 객단가 추이를 구하라
select date_trunc('month',o.order_date)::date as month_
	 , sum(o.total_amount) as month_amount
	 , count(*) as month_order
	 , round(sum(o.total_amount)/count(*),2) as 객단가
  from orders o
 group by date_trunc('month',o.order_date)
 order by 1 asc
 ;
 
 
 -- 미배송(결제완료+배송중) 주문이 많은 지역 상위 10개를 구하라
select o.shipping_city as "지역"
	 , count(*) as "결제완료 배송중 주문수"
  from orders o
 where o.status in ('결제완료','배송중')
 group by o.shipping_city 
 order by 2 desc, o.shipping_city asc
 limit 10
;

-- RFM점수를 기준으로 고객을 명명된 새그먼트로 분류하고 세그먼트 별 고객 수를 구하라.
with RFM as (
	select o.customer_id 
		 , date_trunc('day',max(max(o.order_date)) over())-date_trunc('day',max(o.order_date)) as R_RFM --얼마나 최근에 구매했는가?
		 , count(*) as F_RFM --얼마나 많이 구매했는가
		 , sum(o.total_amount) as M_RFM
	  from orders o
	 where o.status not in ('취소','환불')
	 group by o.customer_id ),
customer_ntile as(
	select RFM.customer_id 
		 , RFM.r_rfm 
		 , ntile(5) over(order by r_rfm desc) as r점수
		 , RFM.f_rfm 
		 , ntile(5) over(order by f_rfm asc) as f점수
		 , RFM.m_rfm 
		 , ntile(5) over(order by m_rfm asc) as m점수
	  from RFM)
select case when cn.r점수>=4 and cn.f점수>=4 and cn.m점수>=4 then '1.핵심VIP'
			when cn.r점수>=4 and cn.f점수>=4 and cn.m점수>=3 then '2.충성'
			when cn.r점수>=4 and cn.f점수>=3 and cn.m점수>=3 then '3,신규·활성'
			when cn.r점수>=3 and cn.f점수>=3 and cn.m점수>=2 then '4,일반'
			when cn.r점수>=1 and cn.f점수>=2 and cn.m점수>=2 then '5.이탈위험'
			else '6.휴면·이탈'
			end as user_grade
	 , count(*) as customer_count
  from customer_ntile cn
  group by 1
  order by 1 asc
;

-- 첫 유효 주문 기준 월별 신규 획득 고객 수를 구하라

select t.first_order as 월
	 , count(*)
  from (
	  select o.customer_id 
		 , date_trunc('month',min(o.order_date))::date as first_order 
	  from orders o
	 where o.status not in ('취소','환불')
	 group by o.customer_id)t
 group by t.first_order 
 order by t.first_order asc
; 
 
 -- 지역 x 등급 교차표 (회원 수)를 합계 상위 10개 지역으로 구하라
select c.city 
	 , count(*) filter(where c.grade='BRONZE')as 브론즈
	 , count(*) filter(where c.grade='SILVER')as 실버
	 , count(*) filter(where c.grade='GOLD') as 골드
	 , count(*) filter(where c.grade='VIP') as VIP수
	 , count(*) as 총합계
  from customers c 
 group by c.city 
 order by count(*) desc
 limit 10
 
 -- 연령대x성별 매출 교차 표를 구하라.
with age_mm as (select extract(year from age(now(),c.birth_date)) as age_
	 , count(distinct c.customer_id) filter(where c.gender='F') as cnt_fgen
	 , sum(o.total_amount) filter(where c.gender='F') as total_sum_fage
	 , count(distinct c.customer_id) filter(where c.gender='M') as cnt_mgen
	 , sum(o.total_amount) filter(where c.gender='M') as total_sum_mage
  from customers c 
  join orders o on c.customer_id = o.customer_id 
 where o.status not in ('취소', '환불')
 group by extract(year from age(now(),c.birth_date)))
select case when am.age_<= 19 then '10대이하' 
	 		when am.age_<= 29 then '20대'
	 		when am.age_<= 39 then '30대'
	 		when am.age_<= 49 then '40대'
	 		when am.age_<= 59 then '50대'
	 		else '60대 이상'
	 		end as age_case
	 , sum(am.cnt_fgen) as 여성회원수
	 , sum(am.total_sum_fage) as 여성총매출
	 , sum(am.cnt_mgen) as 남성회원수
	 , sum(am.total_sum_mage) as 남성총매출
  from age_mm am
 group by 1
 order by 1 asc
;

--고객별 최다 매출 카테고리(대표 카테고리)의 고객 수 분포를 구하라
with cat_cus as 
	(select c.customer_id 
		 , c."name" as cus_name 
		 , c2.category_id 
		 , c2."name" as cat_name
		 , sum(oi.quantity*oi.unit_price) as amount
	  from customers c 
	  join orders o on o.customer_id =c.customer_id 
	  join order_items oi on oi.order_id =o.order_id 
	  join products p on p.product_id =oi.product_id
	  join categories c2 on p.category_id =c2.category_id
	 where o.status not in ('취소','환불')
	  group by c.customer_id , c."name" , c2.category_id ,c2."name" 
	  ),
ranked as (
	 select cc.customer_id
	 	  , cc.category_id
	 	  , cc.cat_name
	 	  , cc.amount
	 	  , row_number() over(partition by cc.customer_id order by amount desc, cc.category_id asc) as rnk
	   from cat_cus cc)
select rnk.cat_name 
	 , count(*) as customer_count
  from ranked as rnk 
 where rnk.rnk =1
 group by rnk.category_id, rnk.cat_name 
 order by customer_count desc, cat_name asc;

-- 휴면(비활성) 회원 중 누적매출 100만원 이상 우수고객 20명을 구하라
select c.customer_id 
	 , c."name"
	 , sum(o.total_amount)
  from customers c 
  join orders o on o.customer_id =c.customer_id 
 where c.is_active is false
   and o.status not in ('취소','환불')
 group by c.customer_id , c."name" 
having sum(o.total_amount)>=1000000
 order by 3 desc 
 limit 20;


--유효주문이 한건도 없는 회원수와 비율을 구하라
with valid_customer as(
	 	select distinct o.customer_id
	 	  from orders o
	 	 where o.status not in ('취소','환불'))
select count(*) filter (where c.customer_id is null)as 무구매회원수
	 , count(*) as 전체회원수
	 , round(100.0*count(*) filter (where c.customer_id is null)/count(*),2) as 비율
  from customers c
  left join valid_customer vc on vc.customer_id =c.customer_id ;

-- 유효판매량이 가장 적은 판매 부진 상품 하위 10개를 구하라
with product_sell as(
	select oi.product_id
		 , sum(oi.quantity) as sell_cnt
	  from order_items oi 
	  join orders o on o.order_id =oi.order_id 
	 where o.status not in ('환불','취소')
	 group by oi.product_id)
select p.product_id 
	 , p."name" 
	 , coalesce(ps.sell_cnt,0) as sum_sell_cnt
  from products p
  left join product_sell ps on ps.product_id =p.product_id 
 order by ps.sell_cnt asc p.product_id asc
 limit 10;

-- 재고가 많은데 판매량이 적은 과잉재고 위험상품(판매중)10개를 구하라
select p.product_id as 품번
	 , p."name" as 상품명
	 , p.stock_quantity as 재고
	 , coalesce(sum(oi.quantity),0) as 판매량
  from products p 
  left join order_items oi on p.product_id  =oi.product_id
 where p.status = '판매중'
  group by p.product_id , p."name" , p.stock_quantity 
  order by p.stock_quantity desc, 4 asc, p.product_id asc
  limit 10;

-- 상품 판매별(판매중/ 품절/ 단종) 과거 매출과 매출 비중(%)을 구하라
select p.status as 상품상태
	 , count(distinct p.product_id) as 상품수
	 , sum(oi.quantity*oi.unit_price)  as 매출
	 , round(100.0*sum(oi.quantity *oi.unit_price)/sum(sum(oi.quantity*oi.unit_price))over()) as 매출비중
  from products p 
  join order_items oi on oi.product_id =p.product_id 
  join orders o on o.order_id = oi.order_id
 where o.status not in ('환불','취소')
 group by p.status
 order by 3 desc;

-- 카테고리별 상품수, 매출, 상품당 평균매출(효율) 효율 내림차순으로 구하라
select c.category_id  as 카테고리번호
	 , c."name"  as 카테고리명
	 , count(distinct p.product_id) as 상품수
	 , sum(oi.quantity *oi.unit_price) as 매출
	 , round(100.0*sum(oi.quantity *oi.unit_price) / count(distinct p.product_id),2) as 상품당평균매출
  from categories c 
  join products p on p.category_id =c.category_id 
  join order_items oi on oi.product_id =p.product_id 
 group by c.category_id, c."name"
 order by 5 desc;

-- 동일 상품을 2회 이상 구매한 고객이 많은 상품 top 10을 구하라
with cus_pro as (
	select c.customer_id
		 , c."name" as cus_name
		 , p.product_id 
		 , p."name" as pro_name
		 , count(distinct o.order_id) as cnt_buy
	  from customers c
	  join orders o on c.customer_id = o.customer_id 
	  join order_items oi on o.order_id =oi.order_id
	  join products p on p.product_id =oi.product_id 
	 where o.status not in ('환불','취소')
	 group by c.customer_id, c."name", p.product_id,p."name")
select cp.product_id 
	 , cp.pro_name 
	 , count(*) filter (where cp.cnt_buy>= 2) as repeat_customer_cnt
  from cus_pro cp 
 group by cp.product_id, cp.pro_name
 order by 3 desc, cp.product_id asc
 limit 10;

-- 상품을 누적 매출 비중으로 A/B/C 등급 분류하고 등급별 상품수 매출 비중을 구하라
with product_buy as(
	select p.product_id 
		 , p."name" 
		 , sum(oi.quantity *oi.unit_price) as buy_pro
	  from products p 
	  join order_items oi on p.product_id =oi.product_id 
	 group by p.product_id, p."name"  
	 order by 3 desc),
pro_ratio as(select pb.product_id 
	 , pb."name" 
	 , pb.buy_pro 
	 , 100.0*sum(pb.buy_pro) over(order by pb.buy_pro desc)/sum(pb.buy_pro) over() as ratio
  from product_buy pb)
select t.등급
	 , count(*) as 상품수
	 , sum(t.buy_pro) as 등급매출
	 , round(100.0* sum(t.buy_pro) / sum(sum(buy_pro)) over(),2) as 메출비중
  from (select pr.product_id 
	 , pr."name" 
	 , case when pr.ratio<=70 then 'A'
			when pr.ratio<=90 then 'B'
			else 'C'
			end as 등급
	, pr.buy_pro 
	, pr.ratio 
  from pro_ratio pr
 order by 3 asc)t
 group by t.등급
 order by t.등급
;