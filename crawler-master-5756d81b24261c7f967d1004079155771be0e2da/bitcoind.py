import requests
import copy
import pdb


class BitClient(object):

    #_requests_tmp = "{\"jsonrpc\":\"1.0\",\"id\":\"1\",\"method\":\"%s\",\"params\":[]}"
    _requests_tmp = {
        "jsonrpc": "1.0",
        "id": "1",
        "method": "",
        "params":[]
    }

    _rpc_host = 'http://127.0.0.1:9332'
    _auth = ('rawpool', 'rawpool2018')
    
    def _call_method(self, method_name , *args):

        rq_data = copy.deepcopy(self._requests_tmp)
        rq_data["method"] = method_name
        rq_data["params"] = list(args)

        resp = requests.post(self._rpc_host, auth=self._auth, json=rq_data).json()
        assert resp["error"] is None
        return resp["result"]


    def getblockhash(self, height):
        return self._call_method("getblockhash" ,height)

    def getblockheader(self, blkhash):
        return self._call_method("getblockheader", blkhash)

if __name__ == '__main__':
    hashstr = BitClient().getblockhash(520000)
    print BitClient().getblockheader(hashstr)
