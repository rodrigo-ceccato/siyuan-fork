import * as assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {resolve} from "node:path";
import {test} from "node:test";
import {runInNewContext} from "node:vm";
import {ModuleKind, transpileModule} from "typescript";
import {SelfHostedFullFeatures} from "./fork";

test("desktop and mobile self-hosted features work without a cloud account", () => {
    const source = readFileSync(resolve(process.cwd(), "src/util/needSubscribe.ts"), "utf8");
    const code = transpileModule(source, {compilerOptions: {module: ModuleKind.CommonJS}}).outputText;
    for (const ios of [false, true]) {
        const exports = {} as {needSubscribe: (tip?: string) => boolean, isPaidUser: () => boolean};
        const window = {siyuan: {user: null as null, languages: {_kernel: {29: "Subscribe"}}}};
        runInNewContext(code, {
            exports,
            window,
            require: (name: string) => {
                if (name === "./fork") {
                    return {SelfHostedFullFeatures};
                }
                if (name.includes("compatibility")) {
                    return {isInIOS: () => ios};
                }
                return {showMessage: () => assert.fail("must not request a subscription")};
            },
        });
        assert.equal(exports.needSubscribe(), false);
        assert.equal(exports.isPaidUser(), true);
        assert.equal(window.siyuan.user, null);
    }
});
