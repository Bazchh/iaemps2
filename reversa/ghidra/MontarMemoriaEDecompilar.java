// Pós-script headless do Ghidra para o IAEmPS2.
// Completa o programa (o ELF importado) com a foto da memória do emulador: dados após o .bss e os módulos
// carregados por fase (código a partir de 0x01000000). Depois analisa tudo, nomeia as âncoras conhecidas e
// decompila as funções pedidas para arquivos de texto.
//
// Argumentos: <foto.bin> <pasta_saida> [nome=endereco ...] -- [endereco ...]
//   nome=endereco   rotula uma função (cria se não existir)
//   endereco        função a decompilar (hexadecimal, com ou sem 0x)
//@category IAEmPS2

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileWriter;
import java.io.InputStream;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

public class MontarMemoriaEDecompilar extends GhidraScript {

    private static final long TAMANHO_EE = 0x2000000L;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            printerr("uso: <foto.bin> <pasta_saida> [nome=endereco ...] -- [endereco ...]");
            return;
        }
        File foto = new File(args[0]);
        File saida = new File(args[1]);
        saida.mkdirs();

        montarMemoria(foto);
        println("analisando...");
        analyzeAll(currentProgram);

        List<String> decompilar = new ArrayList<>();
        boolean depoisDoSeparador = false;
        for (int i = 2; i < args.length; i++) {
            String a = args[i];
            if (a.equals("--")) { depoisDoSeparador = true; continue; }
            if (!depoisDoSeparador && a.startsWith("simbolos:")) {  // simbolos:<csv> endereco,nome,... aplica nomes
                aplicarSimbolos(new File(a.substring(9)));
            } else if (!depoisDoSeparador && a.startsWith("refrescar:")) {  // refrescar:inicio-fim recarrega os bytes da faixa a partir da foto
                String[] par = a.substring(10).split("-", 2);
                refrescar(foto, endereco(par[0]), endereco(par[1]));
            } else if (!depoisDoSeparador && a.startsWith("codigo:")) {  // codigo:inicio-fim marca a faixa como código
                String[] par = a.substring(7).split("-", 2);
                marcarCodigo(endereco(par[0]), endereco(par[1]));
            } else if (!depoisDoSeparador && a.contains(":")) {  // nome:endereco (o cmd.exe parte argumentos em '=')
                String[] par = a.split(":", 2);
                rotular(par[0], par[1]);
            } else {
                decompilar.add(a);
            }
        }

        if (houveCodigoNovo) {
            println("analisando as faixas de código novas...");
            analyzeAll(currentProgram);
        }
        exportarListaDeFuncoes(new File(saida, "funcoes.csv"));

        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        try {
            List<Function> fila = new ArrayList<>();
            for (String e : decompilar) {
                boolean comChamadores = e.startsWith("+");  // +endereco: a função e quem a chama ('^' é escape do cmd)
                Address addr = endereco(comChamadores ? e.substring(1) : e);
                Function f = getFunctionContaining(addr);
                if (f == null) f = createFunction(addr, null);
                if (f == null) { printerr("sem função em " + e); continue; }
                fila.add(f);
                if (comChamadores) fila.addAll(f.getCallingFunctions(monitor));
            }
            for (Function f : fila) {
                DecompileResults r = dec.decompileFunction(f, 120, monitor);
                String nomeSeguro = f.getName().replaceAll("[^A-Za-z0-9_]+", "_");  // "::" não vale em nome de arquivo
                File arq = new File(saida, String.format("%08x_%s.c", f.getEntryPoint().getOffset(), nomeSeguro));
                try (PrintWriter w = new PrintWriter(new FileWriter(arq))) {
                    if (r.decompileCompleted()) {
                        w.print(r.getDecompiledFunction().getC());
                    } else {
                        w.println("// falhou: " + r.getErrorMessage());
                    }
                }
                println("decompilada " + f.getName() + " -> " + arq.getName());
            }
        } finally {
            dec.dispose();
        }
    }

    private void montarMemoria(File foto) throws Exception {
        Memory mem = currentProgram.getMemory();
        long fimDoElf = 0;
        for (MemoryBlock b : mem.getBlocks()) {
            long inicio = b.getStart().getOffset();
            // só os blocos do próprio executável (abaixo de 0x01000000); ignora os meus e os registradores mapeados
            if (inicio < 0x01000000L && !b.isOverlay()) {
                fimDoElf = Math.max(fimDoElf, b.getEnd().getOffset() + 1);
            }
        }
        println(String.format("fim do executável na memória: 0x%x", fimDoElf));
        // código dos módulos carregados por fase (inimigos etc.) visto ao vivo entre 0x01B00000 e 0x01C80000
        long inicioModulos = 0x01B00000L;
        long fimModulos = 0x01D00000L;
        criarBloco(mem, foto, "dados_vivos", fimDoElf, inicioModulos - fimDoElf, false);
        criarBloco(mem, foto, "modulos", inicioModulos, fimModulos - inicioModulos, true);
        criarBloco(mem, foto, "dados_altos", fimModulos, TAMANHO_EE - fimModulos, false);
    }

    private void criarBloco(Memory mem, File foto, String nome, long inicio, long tamanho, boolean executavel) throws Exception {
        if (tamanho <= 0) return;
        Address addr = toAddr(inicio);
        if (mem.getBlock(nome) != null || mem.getBlock(addr) != null) {  // já criado (talvez recortado e renomeado)
            println("bloco " + nome + " já existe");
            return;
        }
        try (InputStream in = new FileInputStream(foto)) {
            long pulados = 0;
            while (pulados < inicio) pulados += in.skip(inicio - pulados);
            MemoryBlock b = mem.createInitializedBlock(nome, addr, in, tamanho, monitor, false);
            b.setRead(true);
            b.setWrite(true);
            b.setExecute(executavel);
            println(String.format("bloco %s: 0x%x..0x%x", nome, inicio, inicio + tamanho));
        }
    }

    private boolean houveCodigoNovo = false;

    // Sobrescreve os bytes de [inicio, fim) com os da foto: serve para módulos carregados depois da foto que criou
    // os blocos (o projeto guarda a foto antiga). Apaga as instruções da faixa para a análise refazê-las.
    private void refrescar(File foto, Address inicio, Address fim) throws Exception {
        long tamanho = fim.getOffset() - inicio.getOffset();
        byte[] dados = new byte[(int) tamanho];
        try (java.io.RandomAccessFile f = new java.io.RandomAccessFile(foto, "r")) {
            f.seek(inicio.getOffset());
            f.readFully(dados);
        }
        currentProgram.getListing().clearCodeUnits(inicio, fim.subtract(1), false);
        currentProgram.getMemory().setBytes(inicio, dados);
        houveCodigoNovo = true;
        println("bytes refrescados: " + inicio + ".." + fim);
    }

    // Recorta a faixa [inicio, fim) do bloco que a contém e a marca como executável, para a análise achar funções nela.
    private void marcarCodigo(Address inicio, Address fim) throws Exception {
        Memory mem = currentProgram.getMemory();
        MemoryBlock b = mem.getBlock(inicio);
        if (b == null) { printerr("sem bloco em " + inicio); return; }
        if (b.isExecute() && b.getStart().equals(inicio)) { println("código já marcado em " + inicio); return; }
        if (!b.getStart().equals(inicio)) mem.split(b, inicio);
        MemoryBlock c = mem.getBlock(inicio);
        if (c.getEnd().add(1).compareTo(fim) > 0) mem.split(c, fim);
        c = mem.getBlock(inicio);
        c.setExecute(true);
        c.setName(String.format("codigo_%08x", inicio.getOffset()));
        houveCodigoNovo = true;
        println("código marcado: " + inicio + ".." + fim);
    }

    private void aplicarSimbolos(File csv) throws Exception {
        int n = 0;
        try (java.io.BufferedReader r = new java.io.BufferedReader(new java.io.FileReader(csv, java.nio.charset.StandardCharsets.UTF_8))) {
            String linha = r.readLine();  // cabeçalho
            while ((linha = r.readLine()) != null) {
                String[] c = linha.split(",", 3);
                if (c.length < 2) continue;
                try { rotular(c[1].replace(' ', '_'), c[0]); n++; } catch (Exception ex) { printerr("símbolo " + linha + ": " + ex.getMessage()); }
            }
        }
        println("símbolos aplicados: " + n);
    }

    private void rotular(String nome, String end) throws Exception {
        Address addr = endereco(end);
        Function f = getFunctionAt(addr);
        if (f == null) f = createFunction(addr, nome);
        if (f != null) f.setName(nome, SourceType.USER_DEFINED);
        else createLabel(addr, nome, true, SourceType.USER_DEFINED);
        println("rótulo " + nome + " em " + addr);
    }

    private void exportarListaDeFuncoes(File arq) throws Exception {
        try (PrintWriter w = new PrintWriter(new FileWriter(arq))) {
            w.println("endereco,nome,tamanho,chamadores");
            FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
            while (it.hasNext()) {
                Function f = it.next();
                w.println(String.format("%08x,%s,%d,%d", f.getEntryPoint().getOffset(), f.getName(),
                    f.getBody().getNumAddresses(), f.getCallingFunctions(monitor).size()));
            }
        }
        println("lista de funções em " + arq);
    }

    private Address endereco(String texto) {
        String t = texto.toLowerCase().startsWith("0x") ? texto.substring(2) : texto;
        return toAddr(Long.parseLong(t, 16));
    }
}
