from __future__ import annotations

from pathlib import Path
import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine

from freshtradeleads.schema import metadata


HEADERS = ["LicenseNo","LastUpdate","BusinessName","BUS-NAME-2","FullBusinessName","MailingAddress","City","State","County","ZIPCode","country","BusinessPhone","BusinessType","IssueDate","ReissueDate","ExpirationDate","InactivationDate","ReactivationDate","PendingSuspension","PendingClassRemoval","PendingClassReplace","PrimaryStatus","SecondaryStatus","Classifications(s)","AsbestosReg","WorkersCompCoverageType","WCInsuranceCompany","WCPolicyNumber","WCEffectiveDate","WCExpirationDate","WCCancellationDate","WCSuspendDate","CBSuretyCompany","CBNumber","CBEffectiveDate","CBCancellationDate","CBAmount","WBSuretyCompany","WBNumber","WBEffectiveDate","WBCancellationDate","WBAmount","DBSuretyCompany","DBNumber","DBEffectiveDate","DBCancellationDate","DBAmount","DateRequired","DiscpCaseRegion","DBBondReason","DBCaseNo","NAME-TP-2"]


@pytest.fixture
def engine(tmp_path):
    e=create_engine(f"sqlite:///{tmp_path/'test.db'}")
    metadata.create_all(e)
    return e


@pytest.fixture
def workbook(tmp_path: Path):
    path=tmp_path/"fixture.xlsx"; wb=Workbook(); ws=wb.active; ws.title="CSLBMasterLicenseData"; ws.append(HEADERS)
    def row(license_no,name,issue,classes,county="Los Angeles",status="CLEAR"):
        data={h:None for h in HEADERS}; data.update({"LicenseNo":license_no,"LastUpdate":"09/03/2026","BusinessName":name,"MailingAddress":"1 MAIN ST","City":"LOS ANGELES","State":"CA","County":county,"ZIPCode":"09001","BusinessPhone":"(213) 555 0100","BusinessType":"Corporation","IssueDate":issue,"ExpirationDate":"09/30/2028","PrimaryStatus":status,"Classifications(s)":classes,"WorkersCompCoverageType":"Exempt","WCEffectiveDate":"09/01/2026","CBSuretyCompany":"TEST SURETY","CBNumber":"B-1","CBEffectiveDate":"09/01/2026","CBAmount":25000})
        return [data[h] for h in HEADERS]
    ws.append(row("001001","Alpha Electric","09/02/2026","B| C10")); ws.append(row("001002","Beta Plumbing","08/30/2026","C36",county="Orange")); ws.append(row("001003","Gamma Electric","07/01/2026","C10"))
    wb.save(path); return path

