#/bin/python

import pdb
import time
import sys
import requests
import MySQLdb
from lxml import etree
from bitcoind import BitClient


def time_str(ts=0):
    if not ts:
        ts = time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

def blk_diff(height):
    blk_hash = BitClient().getblockhash(height)
    return BitClient().getblockheader(blk_hash)["difficulty"]

class BlockParser(object):

    def __init__(self, host, user, passwd, dbname, port=3306, start_time=0, end_time=0):
        self.conn = MySQLdb.connect(host=host, user=user, passwd=passwd, port=port)
        self.cursor = self.conn.cursor()
        self.cursor.execute("use %s;" % dbname)
        self.block_time = dict()

        if end_time == 0:
            self.end_time = time.time()
        else:
            self.end_time = end_time

        if start_time == 0:
            self.start_time = self.end_time - 86400 * 3
        else:
            self.start_time = start_time

        if self.start_time + 3600 >= self.end_time:
            raise Exception("time range is too short")
    
    def process_one_record(self, cursor, ele):
        params = self.generate_colume_tuple(ele)
        sql = self.generate_sql_tpl()
        cursor.execute(sql % params)

    def run(self):

        # GMT+8 2009-01-03 00:00:00
        # start_time = 1230912000 
        # end_time = time.time()
        # start_time = end_time - 86400 * 2
        while self.start_time <= self.end_time:
            day_query = time.strftime("%F", time.localtime(self.start_time))
            print "crawling block for %s" % day_query 
            resp = requests.get("%s?date=%s" % (self.url, day_query))
            html = etree.HTML(resp.text)
            lines = html.xpath('//table/tr')
            lines.pop(0)
            lines.reverse()    
            for tr_ele in lines:
                self.process_one_record(self.cursor, tr_ele)
    
            self.conn.commit()
            self.start_time += 86400
 

class BchParser(BlockParser):

    url = 'http://bch.btc.com/block'

    def generate_sql_tpl(self):
        return """
          insert into bch_block(height, reporter, number, size, fee_avg, basic_reward, fee_reward, blktime, blk_diff, seconds_cost)
          VALUES ('%s', '%s', '%s', '%s', '%f', '%.1f', '%f', '%s', %s, %s) on duplicate key update
          height = values(height), reporter=values(reporter),number=values(number),size=values(size),
          fee_avg=values(fee_avg), basic_reward=values(basic_reward),fee_reward=values(fee_reward),
          blktime=values(blktime), blk_diff=values(blk_diff), seconds_cost=values(seconds_cost);
        """
    def generate_colume_tuple(self, ele):
        basic_reward, fee_reward = ele.xpath('td[6]')[0].text.strip().split('+')
        fee_addition = ele.xpath('td[6]/span')[0].text.strip()
        h = int(ele.xpath('td[1]/a')[0].text.strip().replace(",", ""))

        self.block_time[h] = int(ele.xpath('td[7]/span/@data-btccom-timestamp')[0])
        if h-1 in self.block_time:
            sec_cost = self.block_time[h] - self.block_time[h-1]
        else:
            sec_cost = "null"

        return (
          h,
          ele.xpath('td[2]//a')[0].text.strip().replace("'", "\\'"),
          int(ele.xpath('td[3]')[0].text.strip().replace(",", "")),
          int(ele.xpath('td[4]')[0].text.strip().replace(',', "")),
          float(ele.xpath('td[5]')[0].text.strip()),
          float(basic_reward),
          float(fee_reward+fee_addition),
          time_str(self.block_time[h]),
          "%.4f "% float(blk_diff(h)),
          sec_cost
        )

class BtcParser(BlockParser):

    url = 'http://btc.com/block'

    def generate_sql_tpl(self):
        return """
          insert into btc_block(height, reporter, number, stripped_size, size, weight, fee_avg, basic_reward, fee_reward, blktime)
          VALUES ('%s', '%s', '%s','%s',  '%s', '%s', '%f', '%.1f', '%f', '%s') on duplicate key update
          height = values(height), reporter=values(reporter),number=values(number), stripped_size = values(stripped_size), size=values(size),
          weight=values(weight), fee_avg=values(fee_avg), basic_reward=values(basic_reward),fee_reward=values(fee_reward),
          blktime=values(blktime);
        """
    def generate_colume_tuple(self, ele):
        basic_reward, fee_reward = ele.xpath('td[8]')[0].text.strip().split('+')
        fee_addition = ele.xpath('td[8]/span')[0].text.strip()
        return (
          int(ele.xpath('td[1]/a')[0].text.strip().replace(",", "")),
          ele.xpath('td[2]//a')[0].text.strip().replace("'", "\\'"),
          int(ele.xpath('td[3]')[0].text.strip().replace(",", "")),
          int(ele.xpath('td[4]')[0].text.strip().replace(",", "")),
          int(ele.xpath('td[5]')[0].text.strip().replace(",", "")),
          int(ele.xpath('td[6]')[0].text.strip().replace(',', "")),
          float(ele.xpath('td[7]')[0].text.strip()),
          float(basic_reward),
          float(fee_reward+fee_addition),
          time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(ele.xpath('td[9]/span/@data-btccom-timestamp')[0])))
        )

   

class PowerParser(BlockParser):
  
    def _crawl_all_btc_power(self):
        resp = requests.get('http://btc.com')
        html = etree.HTML(resp.text)
        result = html.xpath('//div[@class="panel-body"]')[2].xpath("//ul[1]/li[1]/dl[1]/dd")[0].text
        power, unit = result.strip().split(' ')
        
        sql = """
          insert into power(ctime, cointype, power, unit, datasource) VALUES(
          '%s', '%s', %s, '%s', '%s');
        """
        self.cursor.execute(sql % (
            time_str(),
            'BTC',
            float(power.strip()),
            unit.strip()[0],
            'btc.com'
        ))

        self.conn.commit()

    def _crawl_btc_btc_power(self):

        resp = requests.get('http://btc.com/stats/pool?pool_mode=day')
        html = etree.HTML(resp.text)
        result = html.xpath('//table[@class]/tr[3]/td[4]')[0].text 
        power, unit = result.strip().split('\n')

        sql = """
          insert into power(ctime, cointype, poolname, power, unit, datasource) VALUES(
          '%s', '%s', '%s', %s, '%s', '%s');
        """
        self.cursor.execute(sql % (
            time_str(),
            'BTC',
            'BTC.com',
            float(power.strip()),
            unit.strip()[0],
            'btc.com'
        ))

        self.conn.commit()

    def _crawl_ant_btc_power(self):
        resp = requests.get('http://antpool.com/webService.htm')
        result = resp.json()['Data']['homeForm']['poolHashrate']
        power, unit = result.split(' ')

        sql = """
          insert into power(ctime, cointype, poolname, power, unit, datasource) VALUES(
          '%s', '%s', '%s', %s, '%s', '%s');
        """
        self.cursor.execute(sql % (
            time_str(),
            'BTC',
            'AntPool',
            float(power.strip()),
            unit.strip()[0],
            'antpool.com'
        ))

        self.conn.commit()

    def _crawl_btctop_btc_power(self):
        resp = requests.get("http://btc.top/api/speed/get_daily_hash_for_all?platform=h5", headers={"Referer": 'http://btc.top/'})
        result = resp.json()
        key = time.strftime("%m-%d", time.gmtime(time.time() - 86400))
        power =  result["data"][key] / 1000 / 1000 / 1000 / 1000 / 1000 

        print power

        sql = """
          insert into power(ctime, cointype, poolname, power, unit, datasource) VALUES(
          '%s', '%s', '%s', %s, '%s', '%s');
        """
        self.cursor.execute(sql % (
            time_str(time.time() - 86400),
            'BTC',
            'BTC.TOP',
            power,
            "P",
            'btc.top'
        ))

        self.conn.commit()

    def _crawl_slush_btc_power(self):
        resp = requests.get("https://slushpool.com/api/v1/web/scalar/statusbar/", json={'coin_type': 'btc'} )
        result = resp.json()
        power = "%.2f" % (result["data"]["btc"]["hr_pool_actual"] / 1000 / 1000)

        sql = """
          insert into power(ctime, cointype, poolname, power, unit, datasource) VALUES(
          '%s', '%s', '%s', %s, '%s', '%s');
        """
        self.cursor.execute(sql % (
            time_str(),
            'BTC',
            'SlushPool',
            power,
            "P",
            'slushpool.com'
        ))

        self.conn.commit()

    def _crawl_f2_btc_power(self):
        resp = requests.get('http://f2pool.com')
        html = etree.HTML(resp.text)
        node = html.xpath("//div[@class='coin-content btc']/div[1]/span")[0]
        power = node.text

        sql = """
          insert into power(ctime, cointype, poolname, power, unit, datasource) VALUES(
          '%s', '%s', '%s', %s, '%s', '%s');
        """
        self.cursor.execute(sql % (
            time_str(),
            'BTC',
            'F2Pool',
            "%.3f" % float(power),
            "P",
            'f2pool.com'
        ))

        self.conn.commit()

    def _crawl_bitcoin_btc_power(self):
        resp = requests.get("https://console.pool.bitcoin.com/srv/stats?")
        rst_dict = {i["coin"]: i["hashrate"] for i in resp.json()['poolCoins']}
        power = rst_dict["BTC"] / 1000 / 1000 / 1000 / 1000 /1000

        sql = """
          insert into power(ctime, cointype, poolname, power, unit, datasource) VALUES(
          '%s', '%s', '%s', %s, '%s', '%s');
        """
        self.cursor.execute(sql % (
            time_str(),
            'BTC',
            'Bitcoin',
            "%.3f" % float(power),
            "P",
            'bitcoin.com'
        ))

        self.conn.commit()

    def run(self):
        self._crawl_all_btc_power()
        self._crawl_btc_btc_power()
        self._crawl_ant_btc_power()
        self._crawl_btctop_btc_power()
        self._crawl_slush_btc_power()
        self._crawl_f2_btc_power()
        self._crawl_bitcoin_btc_power()


class RewardtParser(BlockParser):

    def _crawl_btccom_reward(self, url, coin_type):
        resp = requests.get(url)
        html = etree.HTML(resp.text)
        rst = html.xpath("//div[@class='panel-body']")[2].xpath("ul[1]/li[3]//dd//span/..")[0]

        prefix = rst.text.split("=")[1].strip()
        suffix = rst.xpath("span")[0].text
        reward = "%.8f" % float(prefix + suffix)
 
        sql = """
          insert into reward(ctime, reward, unit, cointype, datasource) 
          VALUES("%s", %s, '%s', '%s', '%s')
        """
        self.cursor.execute(sql % (time_str(), reward, "T*24H", coin_type, "btc.com")) 
        self.conn.commit()

    def crawl_bch_reward(self):
        self._crawl_btccom_reward('http://bch.btc.com/', 'BCH')

    def crawl_btc_reward(self):
        self._crawl_btccom_reward('http://btc.com/', 'BTC')

    def run(self):
        self.crawl_bch_reward()
        self.crawl_btc_reward()
 
def crawl_once(clsname, params_dict):
    crawler = eval("%s(**params_dict)" % clsname)
    crawler.run()    

def main():

    if len(sys.argv) < 2:
        print "usage: %s ParserName1 [Parsername2]" % sys.argv[0]
        return -1

    init_bags = dict(dbname="bch_statistics", 
        host="rm-2ze3tyiox78219w61.mysql.rds.aliyuncs.com", 
        user="bch_crawler", 
        passwd="cwkyg6snl6mLKm",
    )

    
    args = sys.argv[1:]

    for parser_name in args:
        crawl_once(parser_name, init_bags)


if __name__ == '__main__':
    main()




